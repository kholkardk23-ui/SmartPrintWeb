import hashlib
import hmac
import io
import json
import pymupdf
import pytest
from app.config import settings
from app.models import Order, OrderStatus
from app.services import razorpay_service


@pytest.fixture(autouse=True)
def force_razorpay_provider(monkeypatch):
    """Ensure Razorpay is the active payment provider for this test suite."""
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "razorpay")


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


def generate_valid_razorpay_signature(razorpay_order_id: str, razorpay_payment_id: str) -> str:
    secret = (settings.RAZORPAY_KEY_SECRET or "").strip().encode("utf-8")
    msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def generate_valid_webhook_signature(raw_body: bytes) -> str:
    secret = (settings.RAZORPAY_WEBHOOK_SECRET or settings.RAZORPAY_KEY_SECRET or "").strip().encode("utf-8")
    return hmac.new(secret, raw_body, hashlib.sha256).hexdigest()


def test_razorpay_checkout_session_creation(client, created_order):
    """Test creating a Razorpay Checkout session for an order."""
    order_id = created_order["order_id"]
    res = client.post(f"/api/payments/{order_id}/checkout")
    assert res.status_code == 200
    data = res.json()

    assert data["provider"] == "razorpay"
    assert data["razorpay_order_id"] is not None
    assert data["razorpay_order_id"].startswith("order_")
    # Rule 9: Do not expose API secrets in frontend
    assert data["razorpay_key_id"] == settings.RAZORPAY_KEY_ID
    assert "razorpay_key_secret" not in data
    assert "razorpay_webhook_secret" not in data
    assert settings.RAZORPAY_KEY_SECRET not in json.dumps(data)


def test_razorpay_signature_verification_success(client, created_order, db_session):
    """Test verifying a valid Razorpay signature confirms the order."""
    order_id = created_order["order_id"]

    # 1. Start checkout
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    assert checkout_res.status_code == 200
    rzp_order_id = checkout_res.json()["razorpay_order_id"]

    # 2. Simulate Razorpay Checkout returning a payment ID and valid signature
    rzp_payment_id = "pay_test_payment_12345"
    valid_sig = generate_valid_razorpay_signature(rzp_order_id, rzp_payment_id)

    # 3. Call dedicated verify-razorpay endpoint
    verify_payload = {
        "razorpay_order_id": rzp_order_id,
        "razorpay_payment_id": rzp_payment_id,
        "razorpay_signature": valid_sig,
    }
    verify_res = client.post(f"/api/payments/{order_id}/verify-razorpay", json=verify_payload)
    assert verify_res.status_code == 200
    data = verify_res.json()

    assert data["payment_status"] == "PAID"
    assert data["order_status"] == "CONFIRMED"
    assert data["payment_reference"] == rzp_payment_id

    # 4. Check DB state
    db_order = db_session.query(Order).filter(Order.order_number == order_id).first()
    assert db_order.status == OrderStatus.CONFIRMED.value
    assert db_order.payment_status == "SUCCESS"
    assert db_order.payment_reference == rzp_payment_id
    assert db_order.payment_timestamp is not None


def test_razorpay_signature_verification_failure_rejects(client, created_order, db_session):
    """Test that a tampered or fake signature is rejected and DOES NOT confirm order."""
    order_id = created_order["order_id"]

    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    rzp_order_id = checkout_res.json()["razorpay_order_id"]

    rzp_payment_id = "pay_fake_payment_99999"
    fake_sig = "fake_tampered_signature_1234567890abcdef"

    verify_payload = {
        "razorpay_order_id": rzp_order_id,
        "razorpay_payment_id": rzp_payment_id,
        "razorpay_signature": fake_sig,
    }
    verify_res = client.post(f"/api/payments/{order_id}/verify-razorpay", json=verify_payload)
    assert verify_res.status_code == 400
    assert "Invalid Razorpay payment signature" in verify_res.json()["detail"]

    # Order must NOT be confirmed
    db_order = db_session.query(Order).filter(Order.order_number == order_id).first()
    assert db_order.status != OrderStatus.CONFIRMED.value
    assert db_order.payment_status != "SUCCESS"


def test_razorpay_webhook_payment_captured(client, created_order, db_session):
    """Test Razorpay webhook event payment.captured automatically confirms order."""
    order_id = created_order["order_id"]

    webhook_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_webhook_test_888",
                    "status": "captured",
                    "amount": int(created_order["total_amount"] * 100),
                    "currency": "INR",
                    "notes": {
                        "order_number": order_id,
                        "order_id": created_order["id"],
                    },
                }
            },
            "order": {
                "entity": {
                    "id": "order_webhook_test_888",
                    "receipt": order_id,
                    "status": "paid",
                }
            },
        },
    }

    raw_body = json.dumps(webhook_payload).encode("utf-8")
    sig = generate_valid_webhook_signature(raw_body)

    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": sig,
    }

    res = client.post("/api/payments/webhook/razorpay", content=raw_body, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    # Verify order is confirmed
    db_order = db_session.query(Order).filter(Order.order_number == order_id).first()
    assert db_order.status == OrderStatus.CONFIRMED.value
    assert db_order.payment_status == "SUCCESS"
    assert db_order.payment_reference == "pay_webhook_test_888"


def test_razorpay_webhook_invalid_signature_rejected(client, created_order, db_session):
    """Test Razorpay webhook with invalid signature returns 400 Bad Request."""
    order_id = created_order["order_id"]

    webhook_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_hacker_attack",
                    "status": "captured",
                    "notes": {"order_number": order_id},
                }
            }
        },
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": "invalid_fake_webhook_signature",
    }

    res = client.post("/api/payments/webhook/razorpay", content=raw_body, headers=headers)
    assert res.status_code == 400
    assert "Invalid webhook signature" in res.json()["detail"]

    # Order must NOT be marked paid
    db_order = db_session.query(Order).filter(Order.order_number == order_id).first()
    assert db_order.status != OrderStatus.CONFIRMED.value


def test_prevent_duplicate_orders(client, created_order):
    """Test creating an order with the same files and options returns the existing pending order."""
    file_ids = created_order["file_ids"]

    # Attempt to create duplicate order with exact same parameters
    duplicate_payload = {
        "file_ids": file_ids,
        "copies": created_order["copies"],
        "color_mode": created_order["color_mode"],
        "duplex": created_order["duplex"],
        "page_range": created_order["page_range"],
    }

    res2 = client.post("/api/orders", json=duplicate_payload)
    assert res2.status_code == 201
    data2 = res2.json()

    # Must return the SAME order number, preventing duplicate database orders
    assert data2["order_number"] == created_order["order_number"]
    assert data2["id"] == created_order["id"]


def test_confirmed_paid_orders_display_for_tablet(client, created_order):
    """Test that paid orders are retrieved with is_paid=True and available for /tablet."""
    order_id = created_order["order_id"]

    # Confirm order via valid Razorpay payment
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    rzp_order_id = checkout_res.json()["razorpay_order_id"]
    rzp_payment_id = "pay_tablet_test_999"
    sig = generate_valid_razorpay_signature(rzp_order_id, rzp_payment_id)

    client.post(
        f"/api/payments/{order_id}/verify-razorpay",
        json={
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": sig,
        },
    )

    # Now latest confirmed order must be this order!
    latest_confirmed = client.get("/api/orders/latest?confirmed_only=true")
    assert latest_confirmed.status_code == 200
    data = latest_confirmed.json()
    assert data["order_number"] == order_id
    assert data["is_paid"] is True
    assert data["status"] in ("CONFIRMED", "PAID")
    assert data["payment_status"] == "PAID"
