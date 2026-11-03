import io
import pytest
import pymupdf
from app.config import settings
from app.models import Order, OrderStatus


@pytest.fixture(autouse=True)
def force_demo_provider(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "demo")


def create_mock_pdf_bytes(page_count: int = 1) -> bytes:
    doc = pymupdf.open()
    for i in range(page_count):
        page = doc.new_page()
        page.insert_text((50, 72), f"SmartPrint Test Document - Page {i + 1}")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def created_order(client):
    """Upload a file and create an order."""
    pdf_bytes = create_mock_pdf_bytes(page_count=2)
    upload_res = client.post(
        "/api/files/upload",
        files={"file": ("test_doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["file_id"]

    order_payload = {
        "file_ids": [file_id],
        "copies": 1,
        "color_mode": "bw",
        "duplex": False,
        "page_range": "all",
    }
    order_res = client.post("/api/orders", json=order_payload)
    assert order_res.status_code == 201
    return order_res.json()


def test_start_dynamic_upi_payment(client, created_order):
    order_id = created_order["order_id"]
    res = client.post(f"/api/payments/{order_id}/start")
    assert res.status_code == 200
    data = res.json()

    assert data["order_number"] == order_id
    assert data["payment_status"] == "PAYMENT_PENDING"
    assert data["amount"] > 0
    assert "upi://" in data["upi_uri"]
    assert "pa=" in data["upi_uri"]
    assert f"am={data['amount']:.2f}" in data["upi_uri"]
    assert data["qr_data"] == data["upi_uri"]


def test_custom_upi_id_in_dynamic_upi(client, created_order, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "UPI_ID", "mybusiness@upi")
    monkeypatch.setattr(settings, "UPI_NAME", "My Print Shop")

    order_id = created_order["order_id"]
    res = client.post(f"/api/payments/{order_id}/start")
    assert res.status_code == 200
    data = res.json()

    assert data["upi_id"] == "mybusiness@upi"
    assert data["upi_name"] == "My Print Shop"
    assert "pa=mybusiness%40upi" in data["upi_uri"] or "pa=mybusiness@upi" in data["upi_uri"]
    assert "pn=My+Print+Shop" in data["upi_uri"] or "pn=My%20Print%20Shop" in data["upi_uri"]


def test_verify_payment_default_ref(client, created_order):
    order_id = created_order["order_id"]
    client.post(f"/api/payments/{order_id}/start")

    verify_res = client.post(f"/api/payments/{order_id}/verify", json={})
    assert verify_res.status_code == 200
    data = verify_res.json()

    assert data["payment_status"] == "PAID"
    assert data["order_status"] in ["CONFIRMED", "PAID", "PRINTING"]
    assert "UPI-" in data["payment_reference"]


def test_payment_status_polling(client, created_order):
    order_id = created_order["order_id"]

    # Before start
    status_res = client.get(f"/api/payments/{order_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["is_paid"] is False

    # Start payment
    client.post(f"/api/payments/{order_id}/start")

    # Verify payment
    client.post(
        f"/api/payments/{order_id}/verify",
        json={"payment_reference": "UTR1234567890"},
    )

    # After verification
    status_res2 = client.get(f"/api/payments/{order_id}/status")
    assert status_res2.status_code == 200
    assert status_res2.json()["is_paid"] is True
    assert status_res2.json()["payment_status"] == "PAID"
    assert status_res2.json()["payment_reference"] == "UTR1234567890"


def test_successful_payment_saves_database_fields(client, created_order, db_session):
    """Verify that successful payment saves transaction ID, timestamp, and CONFIRMED status."""
    order_id = created_order["order_id"]
    client.post(f"/api/payments/{order_id}/start")

    utr = "KOTAK9823555453UTR123"
    verify_res = client.post(
        f"/api/payments/{order_id}/verify",
        json={"payment_reference": utr},
    )
    assert verify_res.status_code == 200
    data = verify_res.json()
    assert data["payment_status"] == "PAID"
    assert data["order_status"] == "CONFIRMED"
    assert data["payment_reference"] == utr
    assert data["payment_timestamp"] is not None

    # Query directly from database
    db_order = (
        db_session.query(Order)
        .filter(Order.order_number == order_id)
        .first()
    )
    assert db_order is not None
    assert db_order.status == "CONFIRMED"
    assert db_order.payment_status == "SUCCESS"
    assert db_order.payment_reference == utr
    assert db_order.payment_timestamp is not None


def test_duplicate_payment_verification_is_idempotent(client, created_order, db_session):
    """Calling verify multiple times should not create duplicates or fail."""
    order_id = created_order["order_id"]
    client.post(f"/api/payments/{order_id}/start")

    # First verification
    res1 = client.post(
        f"/api/payments/{order_id}/verify",
        json={"payment_reference": "UTR_FIRST_123"},
    )
    assert res1.status_code == 200
    assert res1.json()["payment_status"] == "PAID"

    # Second verification with same or different ref
    res2 = client.post(
        f"/api/payments/{order_id}/verify",
        json={"payment_reference": "UTR_SECOND_456"},
    )
    assert res2.status_code == 200
    assert res2.json()["payment_status"] == "PAID"
    assert res2.json()["order_status"] in ["CONFIRMED", "PAID", "PRINTING"]
    assert res2.json()["payment_reference"] == "UTR_FIRST_123"


def test_failed_and_cancelled_payment_handling(client, created_order, db_session):
    """Verify orders in FAILED or CANCELLED status reject verification."""
    order_id = created_order["order_id"]

    order = (
        db_session.query(Order)
        .filter(Order.order_number == order_id)
        .first()
    )
    order.status = OrderStatus.CANCELLED.value
    order.payment_status = "CANCELLED"
    db_session.commit()

    res = client.post(f"/api/payments/{order_id}/verify", json={})
    assert res.status_code == 400
    assert "cancelled" in res.json()["detail"].lower()


def test_legacy_enum_status_can_still_be_paid(client, created_order, db_session):
    """Rows created by older code may store 'OrderStatus.CREATED'."""
    order_id = created_order["order_id"]

    order = (
        db_session.query(Order)
        .filter(Order.order_number == order_id)
        .first()
    )
    assert order is not None

    order.status = "OrderStatus.CREATED"
    db_session.commit()

    start_res = client.post(f"/api/payments/{order_id}/start")
    assert start_res.status_code == 200
    assert start_res.json()["payment_status"] == "PAYMENT_PENDING"

    verify_res = client.post(f"/api/payments/{order_id}/verify", json={})
    assert verify_res.status_code == 200
    assert verify_res.json()["order_status"] in ["CONFIRMED", "PAID", "PRINTING"]

    order_res = client.get(f"/api/orders/{order_id}")
    assert order_res.status_code == 200
    assert order_res.json()["status"] in ["CONFIRMED", "PRINTING"]
    assert order_res.json()["is_paid"] is True
