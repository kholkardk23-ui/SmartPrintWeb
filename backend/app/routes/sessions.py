import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Printer, PrinterSession, FileRecord


router = APIRouter(
    prefix="/api/sessions",
    tags=["Printer Sessions"],
)


# These statuses mean the customer still owns the printer session.
ACTIVE_SESSION_STATUSES = [
    "WAITING_FOR_UPLOAD",
    "FILE_UPLOADED",
    "OPTIONS_SELECTED",
    "PAYMENT_PENDING",
    "PAID",
    "QUEUED",
    "PRINTING",
]


@router.post("/{machine_code}")
def create_printer_session(
    machine_code: str,
    db: Session = Depends(get_db),
):
    """Allow only one active customer session per printer."""

    printer = (
        db.query(Printer)
        .filter(Printer.machine_code == machine_code)
        .with_for_update()
        .first()
    )

    if not printer:
        raise HTTPException(
            status_code=404,
            detail="Printer not found.",
        )

    if not printer.is_active:
        raise HTTPException(
            status_code=400,
            detail="Printer is inactive.",
        )

    # Prevent a second customer from starting while the printer
    # already has an active customer session.
    active_session = (
        db.query(PrinterSession)
        .filter(
            PrinterSession.printer_id == printer.id,
            PrinterSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .first()
    )

    if active_session:
        raise HTTPException(
            status_code=409,
            detail=(
                "SmartPrint is currently busy with another customer. "
                "Please wait until the current order is completed."
            ),
        )

    session = PrinterSession(
        id=str(uuid.uuid4()),
        printer_id=printer.id,
        file_id=None,
        status="WAITING_FOR_UPLOAD",
    )

    db.add(session)

    try:
        db.commit()
        db.refresh(session)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not create printer session. Please try again.",
        )

    return {
        "session_id": session.id,
        "machine_code": printer.machine_code,
        "printer_name": printer.name,
        "status": session.status,
    }


@router.get("/{session_id}")
def get_printer_session(
    session_id: str,
    db: Session = Depends(get_db),
):
    """Get session status and uploaded file information."""

    session = (
        db.query(PrinterSession)
        .filter(PrinterSession.id == session_id)
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Printer session not found.",
        )

    response = {
        "session_id": session.id,
        "status": session.status,
        "file_id": session.file_id,
    }

    if session.file_id:
        file_record = (
            db.query(FileRecord)
            .filter(FileRecord.id == session.file_id)
            .first()
        )

        if file_record:
            response.update({
                "filename": file_record.original_filename,
                "page_count": file_record.page_count,
                "file_size": file_record.file_size,
            })

    return response