import os
import uuid
import re
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import FileRecord, PrinterSession
from app.schemas import FileUploadResponse
from app.services.pdf_service import pdf_service, PDFProcessingError

router = APIRouter(prefix="/api/files", tags=["Files"])

CHUNK_SIZE = 1024 * 64  # 64 KB chunks for streaming


def sanitize_filename(filename: str) -> str:
    """Sanitize the uploaded file's original name to prevent path traversal or unsafe characters."""
    base = os.path.basename(filename.strip())
    base = re.sub(r"[\x00-\x1f\x7f]", "", base)
    base = base.replace("/", "_").replace("\\", "_")
    return base if base else "document.pdf"


async def process_single_pdf(file: UploadFile, db: Session) -> FileUploadResponse:
    """Validate, inspect, store, and record a single uploaded PDF."""
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Please upload a PDF file. ('{filename}' is not a PDF)",
        )

    # 1. Read file content and validate size
    max_bytes = settings.max_file_size_bytes
    total_size = 0
    file_bytes = bytearray()

    try:
        while chunk := await file.read(CHUNK_SIZE):
            total_size += len(chunk)
            if total_size > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"File size must be {settings.MAX_FILE_SIZE_MB} MB or less. ('{filename}')",
                )
            file_bytes.extend(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"We couldn't upload your file. Please try again. ('{filename}')",
        ) from exc

    # 2. Check for empty file
    if total_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The uploaded file is empty. Please upload a valid PDF. ('{filename}')",
        )

    # 3. Check PDF magic bytes (%PDF-)
    if not pdf_service.validate_pdf_header(bytes(file_bytes[:8])):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Please upload a valid PDF file. ('{filename}' is not a valid PDF)",
        )

    # 4. Verify integrity and extract page count using PyMuPDF
    try:
        page_count = pdf_service.get_pdf_page_count_from_bytes(bytes(file_bytes))
    except PDFProcessingError as pe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error in '{filename}': {str(pe)}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or corrupted PDF file '{filename}'. Please try another file.",
        ) from exc

    # 5. Save file to disk with safe UUID filename
    file_id = str(uuid.uuid4())
    stored_filename = f"{file_id}.pdf"
    stored_filepath = os.path.join(settings.UPLOAD_DIR, stored_filename)

    try:
        with open(stored_filepath, "wb") as f:
            f.write(file_bytes)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save '{filename}' on server. Please try again.",
        ) from exc

    # 6. Save metadata record to SQLite database
    sanitized_name = sanitize_filename(filename)
    record = FileRecord(
        id=file_id,
        original_filename=sanitized_name,
        stored_filename=stored_filename,
        file_size=total_size,
        page_count=page_count,
        status="uploaded",
    )

    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception as exc:
        if os.path.exists(stored_filepath):
            try:
                os.remove(stored_filepath)
            except OSError:
                pass
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save details for '{filename}'. Please try again.",
        ) from exc

    return FileUploadResponse(
        file_id=record.id,
        original_filename=record.original_filename,
        file_size=record.file_size,
        page_count=record.page_count,
        status=record.status,
    )


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a single customer PDF document",
    description="Validates, processes, and stores an uploaded PDF file, returning page count and metadata.",
)
async def upload_file(
    file: UploadFile = File(..., description="PDF document (max 50 MB)"),
    db: Session = Depends(get_db),
):
    """Handle a single customer PDF upload."""
    return await process_single_pdf(file, db)


@router.post(
    "/upload/{session_id}",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF to a specific printer session",
    description="Uploads a customer PDF and attaches it to the selected printer session.",
)
async def upload_file_to_session(
    session_id: str,
    file: UploadFile = File(..., description="PDF document (max 50 MB)"),
    db: Session = Depends(get_db),
):
    """Upload a PDF and attach it to a specific printer session."""

    session = (
        db.query(PrinterSession)
        .filter(PrinterSession.id == session_id)
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Printer session not found.",
        )

    if session.status != "WAITING_FOR_UPLOAD":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This printer session is not accepting uploads. Current status: {session.status}",
        )

    # Process and store the PDF using the existing upload logic.
    result = await process_single_pdf(file, db)

    # Attach the uploaded file to this printer session.
    session.file_id = result.file_id
    session.status = "FILE_UPLOADED"

    try:
        db.commit()
        db.refresh(session)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File was uploaded, but could not be attached to the printer session.",
        ) from exc

    return result
@router.get(
    "/{file_id}",
    summary="Retrieve an uploaded PDF",
    description="Returns the uploaded PDF file for viewing or printing.",
)
async def get_uploaded_file(
    file_id: str,
    db: Session = Depends(get_db),
):
    """Return an uploaded PDF file by its file ID."""

    record = (
        db.query(FileRecord)
        .filter(FileRecord.id == file_id)
        .first()
    )

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found.",
        )

    filepath = os.path.join(settings.UPLOAD_DIR, record.stored_filename)

    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded file is missing from the server.",
        )

    return FileResponse(
        path=filepath,
        media_type="application/pdf",
        filename=record.original_filename,
        content_disposition_type="inline",
    )
async def upload_multiple_files(
    files: List[UploadFile] = File(..., description="Multiple PDF documents (max 50 MB each)"),
    db: Session = Depends(get_db),
):
    """Handle multiple customer PDF uploads in a single request."""
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files were provided for upload.",
        )

    results: List[FileUploadResponse] = []
    for f in files:
        res = await process_single_pdf(f, db)
        results.append(res)

    return results
