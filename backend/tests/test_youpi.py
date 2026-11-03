import hashlib
import hmac
import io
import json
import pymupdf
import pytest
from app.config import settings
from app.models import Order, OrderStatus
from app.services import youpi_service


def create_mock_pdf_bytes(page_count: int = 1) -> bytes:
    doc = pymupdf.open()
    for i in range(page_count):
        page = doc.new_page()
        page.insert_text((50, 72), f"SmartPrint YouPI Test Document - Page {i + 1}")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def created_order(client):
    """Upload a file and create an order for YouPI payment testing."""
    pdf_bytes = create_mock_pdf_bytes(page_count=3)
    upload_res = client.post(
        "/api/files/upload",
        files={"file": ("youpi_test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["file_id"]

    order_payload = {
        "file_ids": [file_id],
        "copies": 2,
        "color_mode": "bw",
        "duplex": False,
        "page_range": "all",
    }
    order_res = client.post("/api/orders", json=order_payload)
    assert order_res.status_code == 201
    return order_res.json()


def get_db_order(db_session, identifier: str) -> Order:
    return db_session.query(Order).filter(
        (Order.id == identifier) | (Order.order_number == identifier)
    ).first()


def generate_valid_youpi_signature(raw_body: bytes, secret: str = None) -> str:
    key = (secret or settings.YOUPI_WEBHOOK_SECRET or "youpi_test_webhook_secret_key_32bytes_long!").strip().encode("utf-8")
    digest = hmac.new(key, raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ==============================================================================
# TEST 1: YouPI Checkout Creation & Dynamic UPI QR
# ==============================================================================
def test_youpi_checkout_session_creation(client, created_order, db_session):
    """1. Test creating YouPI-PG payment session with dynamic UPI URI."""
    order_id = created_order["order_id"]
    res = client.post(f"/api/payments/{order_id}/checkout?provider=youpi")
    assert res.status_code == 200
    data = res.json()

    assert data["provider"] == "youpi"
    assert data["payment_session_id"] is not None
    assert data["upi_uri"] is not None
    assert data["upi_uri"].startswith("upi://pay")
    assert "am=" in data["upi_uri"]
    assert str(int(created_order["total_amount"])) in data["upi_uri"]

    # Verify session ID was saved to MySQL Order
    db_order = get_db_order(db_session, order_id)
    assert db_order is not None
    assert db_order.payment_session_id is not None
    assert db_order.status == OrderStatus.PAYMENT_PENDING.value


# ==============================================================================
# TEST 2: Successful Mock UPI Webhook & Order Confirmation
# ==============================================================================
def test_successful_mock_upi_payment(client, created_order, db_session):
    """2. Test valid YouPI webhook event confirms order with payment_status=SUCCESS and is_paid=True."""
    order_id = created_order["order_id"]
    order_num = created_order["order_number"]
    amount = created_order["total_amount"]
    utr = "612345678901"

    webhook_payload = {
        "event": "OBSERVED_SUCCESS",
        "deliveryId": f"del_{order_id}",
        "orderId": order_num,
        "paymentId": f"youpi_pay_{order_id[:8]}",
        "amount": amount,
        "currency": "INR",
        "utr": utr,
        "timestamp": 1793607000000,
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    sig = generate_valid_youpi_signature(raw_body)

    res = client.post(
        "/api/payments/webhook/youpi",
        content=raw_body,
        headers={"X-Gateway-Signature": sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "ok"
    assert res_data["order_status"] == "CONFIRMED"
    assert res_data["payment_status"] == "SUCCESS"
    assert res_data["is_paid"] is True

    # Check database state
    db_order = get_db_order(db_session, order_id)
    assert db_order is not None
    assert db_order.status == OrderStatus.CONFIRMED.value
    assert db_order.payment_status == "SUCCESS"
    assert db_order.is_paid is True
    assert db_order.payment_reference == utr


# ==============================================================================
# TEST 3: Failed Payment Webhook Event
# ==============================================================================
def test_failed_payment_webhook(client, created_order, db_session):
    """3. Test YouPI FAILED webhook updates order and payment status to FAILED."""
    order_id = created_order["order_id"]
    order_num = created_order["order_number"]
    webhook_payload = {
        "event": "FAILED",
        "deliveryId": f"del_failed_{order_id}",
        "orderId": order_num,
        "paymentId": "youpi_pay_failed",
        "amount": created_order["total_amount"],
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    sig = generate_valid_youpi_signature(raw_body)

    res = client.post(
        "/api/payments/webhook/youpi",
        content=raw_body,
        headers={"X-Gateway-Signature": sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 200

    db_order = get_db_order(db_session, order_id)
    assert db_order is not None
    assert db_order.status == OrderStatus.FAILED.value
    assert db_order.payment_status == "FAILED"
    assert db_order.is_paid is False


# ==============================================================================
# TEST 4: Expired / Cancelled Payment Webhook Event
# ==============================================================================
def test_expired_and_cancelled_payment_webhook(client, created_order, db_session):
    """4. Test YouPI EXPIRED and CANCELLED webhook events."""
    order_id = created_order["order_id"]
    order_num = created_order["order_number"]
    webhook_payload = {
        "event": "EXPIRED",
        "deliveryId": f"del_exp_{order_id}",
        "orderId": order_num,
        "paymentId": "youpi_pay_exp",
        "amount": created_order["total_amount"],
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    sig = generate_valid_youpi_signature(raw_body)

    res = client.post(
        "/api/payments/webhook/youpi",
        content=raw_body,
        headers={"X-Gateway-Signature": sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 200

    db_order = get_db_order(db_session, order_id)
    assert db_order is not None
    assert db_order.status == OrderStatus.CANCELLED.value
    assert db_order.payment_status == "CANCELLED"
    assert db_order.is_paid is False


# ==============================================================================
# TEST 5: Pending Payment Status Polling
# ==============================================================================
def test_pending_payment_status_polling(client, created_order):
    """5. Test polling status returns pending status when payment not yet observed."""
    order_id = created_order["order_id"]
    # Start payment
    client.post(f"/api/payments/{order_id}/checkout?provider=youpi")

    res = client.get(f"/api/payments/{order_id}/status")
    assert res.status_code == 200
    data = res.json()
    assert data["payment_status"] in ("PENDING", "PAYMENT_PENDING")
    assert data["is_paid"] is False
    assert data["amount"] == created_order["total_amount"]


# ==============================================================================
# TEST 6: Invalid Webhook Signature Rejection
# ==============================================================================
def test_invalid_webhook_signature_rejected(client, created_order):
    """6. Test webhook with invalid HMAC signature is strictly rejected with HTTP 400."""
    webhook_payload = {
        "event": "SUCCESS",
        "orderId": created_order["order_number"],
        "amount": created_order["total_amount"],
        "utr": "612345678901",
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    invalid_sig = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

    res = client.post(
        "/api/payments/webhook/youpi",
        content=raw_body,
        headers={"X-Gateway-Signature": invalid_sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 400
    assert "Invalid YouPI webhook signature" in res.json()["detail"]


# ==============================================================================
# TEST 7: Wrong Payment Amount Rejection
# ==============================================================================
def test_wrong_payment_amount_rejected(client, created_order, db_session):
    """7. Test webhook reporting a mismatched payment amount is rejected with HTTP 400."""
    order_id = created_order["order_id"]
    wrong_amount = float(created_order["total_amount"]) + 50.0  # Mismatched amount
    webhook_payload = {
        "event": "SUCCESS",
        "orderId": created_order["order_number"],
        "amount": wrong_amount,
        "utr": "612345678902",
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    sig = generate_valid_youpi_signature(raw_body)

    res = client.post(
        "/api/payments/webhook/youpi",
        content=raw_body,
        headers={"X-Gateway-Signature": sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 400
    assert "Payment amount mismatch" in res.json()["detail"]

    # Order must NOT be marked paid
    db_order = get_db_order(db_session, order_id)
    assert db_order is not None
    assert db_order.is_paid is False
    assert db_order.status != OrderStatus.CONFIRMED.value


# ==============================================================================
# TEST 8: Duplicate UTR Detection Across Orders
# ==============================================================================
def test_duplicate_utr_across_orders_rejected(client, created_order, db_session):
    """8. Test reusing the same bank UTR for a second order is rejected with HTTP 409 Conflict."""
    utr = "777888999111"

    # First order payment succeeds with UTR
    raw_body1 = json.dumps({
        "event": "SUCCESS",
        "orderId": created_order["order_number"],
        "amount": created_order["total_amount"],
        "utr": utr,
    }).encode("utf-8")
    sig1 = generate_valid_youpi_signature(raw_body1)

    res1 = client.post(
        "/api/payments/webhook/youpi",
        content=raw_body1,
        headers={"X-Gateway-Signature": sig1, "Content-Type": "application/json"},
    )
    assert res1.status_code == 200

    # Create a second order
    pdf_bytes = create_mock_pdf_bytes(page_count=1)
    upload_res = client.post("/api/files/upload", files={"file": ("order2.pdf", io.BytesIO(pdf_bytes), "application/pdf")})
    file_id2 = upload_res.json()["file_id"]
    order2_res = client.post("/api/orders", json={"file_ids": [file_id2], "copies": 1, "color_mode": "bw"})
    order2 = order2_res.json()

    # Attempt to use the same UTR for order 2 -> must reject with 409
    raw_body2 = json.dumps({
        "event": "SUCCESS",
        "orderId": order2["order_number"],
        "amount": order2["total_amount"],
        "utr": utr,
    }).encode("utf-8")
    sig2 = generate_valid_youpi_signature(raw_body2)

    res2 = client.post(
        "/api/payments/webhook/youpi",
        content=raw_body2,
        headers={"X-Gateway-Signature": sig2, "Content-Type": "application/json"},
    )
    assert res2.status_code == 409
    assert "Duplicate UTR reference" in res2.json()["detail"]


# ==============================================================================
# TEST 9: Duplicate Webhook Delivery Idempotency
# ==============================================================================
def test_duplicate_webhook_delivery_idempotency(client, created_order):
    """9. Test redelivery of the same webhook delivery ID is handled idempotently without error."""
    raw_body = json.dumps({
        "event": "SUCCESS",
        "deliveryId": "del_unique_idempotency_12345",
        "orderId": created_order["order_number"],
        "amount": created_order["total_amount"],
        "utr": "999888777666",
    }).encode("utf-8")
    sig = generate_valid_youpi_signature(raw_body)

    # First delivery
    res1 = client.post(
        "/api/payments/webhook/youpi",
        content=raw_body,
        headers={"X-Gateway-Signature": sig, "Content-Type": "application/json"},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "ok"

    # Duplicate delivery with same delivery ID -> must return idempotent response without reprocessing
    res2 = client.post(
        "/api/payments/webhook/youpi",
        content=raw_body,
        headers={"X-Gateway-Signature": sig, "Content-Type": "application/json"},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] in ("already_paid", "ignored")


# ==============================================================================
# TEST 10: Tablet Dashboard Confirmed Order Query
# ==============================================================================
def test_confirmed_paid_order_visible_on_tablet(client, created_order):
    """10. Test confirmed paid orders are returned by /api/orders for /tablet dashboard display."""
    order_id = created_order["order_id"]
    order_num = created_order["order_number"]

    # Confirm order via YouPI webhook
    raw_body = json.dumps({
        "event": "OBSERVED_SUCCESS",
        "orderId": order_num,
        "amount": created_order["total_amount"],
        "utr": "912345678909",
    }).encode("utf-8")
    sig = generate_valid_youpi_signature(raw_body)
    client.post(
        "/api/payments/webhook/youpi",
        content=raw_body,
        headers={"X-Gateway-Signature": sig, "Content-Type": "application/json"},
    )

    # Fetch orders list (used by TabletDashboard.jsx)
    orders_res = client.get("/api/orders")
    assert orders_res.status_code == 200
    orders = orders_res.json()

    # Find confirmed order
    found = next((o for o in orders if o["order_id"] == order_id or o.get("order_number") == order_num), None)
    assert found is not None
    assert found["status"] == "CONFIRMED"
    assert found["payment_status"] in ("PAID", "SUCCESS")
    assert found["is_paid"] is True
    assert found["total_amount"] == created_order["total_amount"]
    assert len(found["documents"]) >= 1
    assert "youpi_test.pdf" in found["documents"][0]["filename"]
