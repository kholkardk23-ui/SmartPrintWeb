import io
import os
import pytest
import pymupdf
from sqlalchemy import select
from app.models import FileRecord
from app.config import settings


def create_mock_pdf_bytes(page_count: int = 1) -> bytes:
    """Helper to generate a real, valid PDF in memory with specified page count."""
    doc = pymupdf.open()
    for i in range(page_count):
        page = doc.new_page()
        page.insert_text((50, 72), f"SmartPrint Test Document - Page {i + 1}")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# 1. Health Endpoint Test (including database report)
def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["ok", "degraded"]
    assert data["service"] == "SmartPrint Backend"
    assert "database" in data


# 2. Database Session and Record Creation & Retrieval Test
def test_database_record_creation_and_retrieval(db_session):
    record = FileRecord(
        id="test-uuid-1234",
        original_filename="sample_test.pdf",
        stored_filename="test-uuid-1234.pdf",
        file_size=10240,
        page_count=5,
        status="uploaded",
    )
    db_session.add(record)
    db_session.commit()

    # Query back
    stmt = select(FileRecord).where(FileRecord.id == "test-uuid-1234")
    fetched = db_session.execute(stmt).scalar_one_or_none()

    assert fetched is not None
    assert fetched.original_filename == "sample_test.pdf"
    assert fetched.page_count == 5
    assert fetched.file_size == 10240
    assert fetched.status == "uploaded"


# 3. Valid PDF Upload & Page Count Test
def test_upload_valid_pdf_single_page(client):
    pdf_bytes = create_mock_pdf_bytes(page_count=1)
    files = {"file": ("assignment.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    response = client.post("/api/files/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "assignment.pdf"
    assert data["page_count"] == 1
    assert data["status"] == "uploaded"
    assert "file_id" in data
    assert data["file_size"] == len(pdf_bytes)


# 4. Multi-page Count Calculation Test (3 pages)
def test_upload_multi_page_pdf(client):
    page_count = 3
    pdf_bytes = create_mock_pdf_bytes(page_count=page_count)
    files = {"file": ("lecture_notes.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    response = client.post("/api/files/upload", files=files)

    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "lecture_notes.pdf"
    assert data["page_count"] == 3
    assert data["status"] == "uploaded"


# 5. Multiple PDF Upload Endpoint Test
def test_upload_multiple_files(client):
    pdf1 = create_mock_pdf_bytes(page_count=2)
    pdf2 = create_mock_pdf_bytes(page_count=4)
    files = [
        ("files", ("doc1.pdf", io.BytesIO(pdf1), "application/pdf")),
        ("files", ("doc2.pdf", io.BytesIO(pdf2), "application/pdf")),
    ]
    response = client.post("/api/files/upload-multiple", files=files)

    assert response.status_code == 201
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["original_filename"] == "doc1.pdf"
    assert data[0]["page_count"] == 2
    assert data[1]["original_filename"] == "doc2.pdf"
    assert data[1]["page_count"] == 4


# 6. Non-PDF Rejection Test
def test_reject_non_pdf_extension(client):
    text_content = b"This is a plain text file, not a PDF."
    files = {"file": ("notes.txt", io.BytesIO(text_content), "text/plain")}
    response = client.post("/api/files/upload", files=files)

    assert response.status_code == 400
    assert "Please upload a PDF file." in response.json()["detail"]


# 7. Invalid Magic Bytes Test (pretending to be .pdf with text content)
def test_reject_fake_pdf(client):
    fake_content = b"Hello world! I am not really a PDF file."
    files = {"file": ("fake.pdf", io.BytesIO(fake_content), "application/pdf")}
    response = client.post("/api/files/upload", files=files)

    assert response.status_code == 400
    assert "Please upload a valid PDF file." in response.json()["detail"]


# 8. Corrupted PDF Handling Test
def test_reject_corrupted_pdf(client):
    corrupted_content = b"%PDF-1.4\nCorrupted binary stream that cannot be opened by PyMuPDF \x00\xff\xfe"
    files = {"file": ("corrupted.pdf", io.BytesIO(corrupted_content), "application/pdf")}
    response = client.post("/api/files/upload", files=files)

    assert response.status_code == 400
    assert "not a valid or readable PDF" in response.json()["detail"] or "Invalid or corrupted" in response.json()["detail"]


# 9. File Size Limit Test (> 10 MB)
def test_reject_oversized_file(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_MB", 1)
    oversized_data = b"%PDF-1.4\n" + (b"A" * (1024 * 1024 + 500))  # Just over 1MB
    files = {"file": ("huge.pdf", io.BytesIO(oversized_data), "application/pdf")}
    response = client.post("/api/files/upload", files=files)

    assert response.status_code == 413
    assert "exceeds the 1 MB limit." in response.json()["detail"] or "1 MB" in response.json()["detail"]
