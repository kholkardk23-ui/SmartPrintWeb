import io
import pytest
import pymupdf
from fastapi.testclient import TestClient
from app.main import app
from app.services.pricing_service import (
    parse_and_validate_page_range,
    calculate_physical_sheets,
    calculate_pricing,
)


def create_mock_pdf_bytes(page_count: int = 1) -> bytes:
    """Helper to generate a real, valid PDF in memory with specified page count."""
    doc = pymupdf.open()
    for i in range(page_count):
        page = doc.new_page()
        page.insert_text((50, 72), f"SmartPrint Test Document - Page {i + 1}")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def uploaded_3page_file(client):
    """Upload a valid 3-page PDF and return file metadata."""
    pdf_bytes = create_mock_pdf_bytes(page_count=3)
    response = client.post(
        "/api/files/upload",
        files={"file": ("assignment.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert response.status_code == 201, f"Upload failed: {response.text}"
    return response.json()


# ==============================================================================
# 1. 3-page B&W single-side = ₹6
# ==============================================================================
def test_order_bw_single_side_3pages(client, uploaded_3page_file):
    payload = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 1,
        "color_mode": "bw",
        "duplex": False,
        "page_range": "all",
    }
    response = client.post("/api/orders", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["selected_page_count"] == 3
    assert data["copies"] == 1
    assert data["color_mode"] == "bw"
    assert data["duplex"] is False
    assert data["physical_sheet_count"] == 3
    assert data["price_per_page"] == 2.0
    assert data["total_amount"] == 6.0
    assert data["currency"] == "INR"
    assert data["status"] == "OPTIONS_SELECTED"


# ==============================================================================
# 2. 3-page B&W, 2 copies = ₹12
# ==============================================================================
def test_order_bw_multiple_copies_3pages(client, uploaded_3page_file):
    payload = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 2,
        "color_mode": "bw",
        "duplex": False,
        "page_range": "all",
    }
    response = client.post("/api/orders", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["selected_page_count"] == 3
    assert data["copies"] == 2
    assert data["physical_sheet_count"] == 6  # 3 * 2
    assert data["price_per_page"] == 2.0
    assert data["total_amount"] == 12.0  # 3 * 2 * 2


# ==============================================================================
# 3. 3-page Colour = ₹15
# ==============================================================================
def test_order_colour_single_side_3pages(client, uploaded_3page_file):
    payload = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 1,
        "color_mode": "color",
        "duplex": False,
        "page_range": "all",
    }
    response = client.post("/api/orders", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["selected_page_count"] == 3
    assert data["copies"] == 1
    assert data["color_mode"] == "color"
    assert data["price_per_page"] == 5.0
    assert data["total_amount"] == 15.0  # 3 * 1 * 5


# ==============================================================================
# 4. 3-page Colour, 2 copies = ₹30
# ==============================================================================
def test_order_colour_multiple_copies_3pages(client, uploaded_3page_file):
    payload = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 2,
        "color_mode": "color",
        "duplex": False,
        "page_range": "all",
    }
    response = client.post("/api/orders", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["selected_page_count"] == 3
    assert data["copies"] == 2
    assert data["price_per_page"] == 5.0
    assert data["total_amount"] == 30.0  # 3 * 2 * 5


# ==============================================================================
# 5. 3-page B&W duplex = ₹6 and 2 physical sheets
# ==============================================================================
def test_order_bw_duplex_3pages(client, uploaded_3page_file):
    payload = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 1,
        "color_mode": "bw",
        "duplex": True,
        "page_range": "all",
    }
    response = client.post("/api/orders", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["selected_page_count"] == 3
    assert data["copies"] == 1
    assert data["duplex"] is True
    assert data["physical_sheet_count"] == 2  # ceil(3/2) * 1 = 2
    assert data["price_per_page"] == 2.0
    assert data["total_amount"] == 6.0


# ==============================================================================
# 6. Custom page range (e.g. "1-2" -> 2 pages)
# ==============================================================================
def test_order_custom_page_range(client, uploaded_3page_file):
    payload = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 1,
        "color_mode": "bw",
        "duplex": False,
        "page_range": "1-2",
    }
    response = client.post("/api/orders", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["selected_page_count"] == 2
    assert data["total_amount"] == 4.0  # 2 * 1 * 2


# ==============================================================================
# 7. Invalid page range syntax
# ==============================================================================
def test_order_invalid_page_range_syntax(client, uploaded_3page_file):
    payload = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 1,
        "color_mode": "bw",
        "duplex": False,
        "page_range": "abc",
    }
    response = client.post("/api/orders", json=payload)
    assert response.status_code == 400
    assert "numeric" in response.json()["detail"].lower() or "invalid" in response.json()["detail"].lower()


# ==============================================================================
# 8. Page range exceeding PDF pages
# ==============================================================================
def test_order_page_range_exceeding_pages(client, uploaded_3page_file):
    payload = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 1,
        "color_mode": "bw",
        "duplex": False,
        "page_range": "1-5",  # Document only has 3 pages
    }
    response = client.post("/api/orders", json=payload)
    assert response.status_code == 400
    assert "exceeds" in response.json()["detail"].lower()


# ==============================================================================
# 9. Invalid copies (< 1 or > 100)
# ==============================================================================
def test_order_invalid_copies(client, uploaded_3page_file):
    # Test copies = 0
    payload_zero = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 0,
        "color_mode": "bw",
        "duplex": False,
        "page_range": "all",
    }
    response = client.post("/api/orders", json=payload_zero)
    assert response.status_code in [400, 422]

    # Test copies = 101
    payload_high = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 101,
        "color_mode": "bw",
        "duplex": False,
        "page_range": "all",
    }
    response = client.post("/api/orders", json=payload_high)
    assert response.status_code in [400, 422]


# ==============================================================================
# 10. Invalid color mode
# ==============================================================================
def test_order_invalid_color_mode(client, uploaded_3page_file):
    payload = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 1,
        "color_mode": "sepia",
        "duplex": False,
        "page_range": "all",
    }
    response = client.post("/api/orders", json=payload)
    assert response.status_code in [400, 422]


# ==============================================================================
# 11. Invalid file_id
# ==============================================================================
def test_order_invalid_file_id(client):
    payload = {
        "file_id": "nonexistent-file-uuid",
        "copies": 1,
        "color_mode": "bw",
        "duplex": False,
        "page_range": "all",
    }
    response = client.post("/api/orders", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ==============================================================================
# 12. Get existing order
# ==============================================================================
def test_get_existing_order(client, uploaded_3page_file):
    # Create order first
    payload = {
        "file_id": uploaded_3page_file["file_id"],
        "copies": 1,
        "color_mode": "bw",
        "duplex": False,
        "page_range": "all",
    }
    create_res = client.post("/api/orders", json=payload)
    assert create_res.status_code == 201
    order_id = create_res.json()["order_id"]

    # Retrieve order
    get_res = client.get(f"/api/orders/{order_id}")
    assert get_res.status_code == 200
    order_data = get_res.json()
    assert order_data["order_id"] == order_id
    assert order_data["file_id"] == uploaded_3page_file["file_id"]
    assert order_data["filename"] == "assignment.pdf"
    assert order_data["total_amount"] == 6.0
    assert order_data["status"] == "OPTIONS_SELECTED"


# ==============================================================================
# 13. Get nonexistent order
# ==============================================================================
def test_get_nonexistent_order(client):
    response = client.get("/api/orders/nonexistent-order-uuid-999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
