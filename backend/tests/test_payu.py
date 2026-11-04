"""
PayU India Payment Gateway Integration Tests
============================================
Verifies:
* Successful payment.
* Failed payment.
* Cancelled payment.
* Invalid payment response / tampered hash.
* Duplicate callback idempotency.
* Independent server-to-server payment verification with PayU.
* Correct order status.
* Order appearing on the existing tablet dashboard.
* Prevention of credential leakage (Salt never exposed).
"""

import hashlib
import io
import json
from unittest.mock import patch, MagicMock

import pymupdf
import pytest

from app.config import settings
from app.models import Order, OrderStatus
from app.services import payu_service


@pytest.fixture(autouse=True)
def force_payu_provider(monkeypatch):
    """Ensure PayU is the active payment provider for this test suite."""
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "payu")
    monkeypatch.setattr(settings, "PAYU_MODE", "test")
    monkeypatch.setattr(settings, "PAYU_MERCHANT_KEY", "TH9CFX")
    monkeypatch.setattr(settings, "PAYU_MERCHANT_SALT", "7a4erhRW6vODP5j7tqa8xQJ3cFpCk40q")
    monkeypatch.setattr(settings, "PAYU_PAYMENT_URL", "https://test.payu.in/_payment")
    monkeypatch.setattr(settings, "PAYU_VERIFY_URL", "https://test.payu.in/merchant/postservice.php?form=2")
    monkeypatch.setattr(settings, "PAYU_SUCCESS_URL", "http://localhost:8000/api/payments/payu/response")
    monkeypatch.setattr(settings, "PAYU_FAILURE_URL", "http://localhost:8000/api/payments/payu/response")
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:5173")


def create_mock_pdf_bytes(page_count: int = 2) -> bytes:
    doc = pymupdf.open()
    for i in range(page_count):
        page = doc.new_page()
        page.insert_text((50, 72), f"SmartPrint PayU Test Document - Page {i + 1}")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def created_order(client):
    """Upload a file and create an order."""
    pdf_bytes = create_mock_pdf_bytes(page_count=3)
    upload_res = client.post(
        "/api/files/upload",
        files={"file": ("test_doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
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


def generate_payu_response_hash(
    status: str,
    txnid: str,
    amount: str,
    productinfo: str,
    firstname: str,
    email: str,
    udf1: str = "",
    udf2: str = "",
    udf3: str = "",
    udf4: str = "",
    udf5: str = "",
    additional_charges: str = "",
    salt: str = "7a4erhRW6vODP5j7tqa8xQJ3cFpCk40q",
    key: str = "TH9CFX",
) -> str:
    """Helper to generate a valid PayU reverse response hash."""
    if additional_charges:
        seq = (
            f"{additional_charges}|{salt}|{status}||||||"
            f"{udf5}|{udf4}|{udf3}|{udf2}|{udf1}|"
            f"{email}|{firstname}|{productinfo}|{amount}|{txnid}|{key}"
        )
    else:
        seq = (
            f"{salt}|{status}||||||"
            f"{udf5}|{udf4}|{udf3}|{udf2}|{udf1}|"
            f"{email}|{firstname}|{productinfo}|{amount}|{txnid}|{key}"
        )
    return hashlib.sha512(seq.encode("utf-8")).hexdigest().lower()


def mock_payu_service_post(mock_data):
    """Mock httpx Client specifically within payu_service."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_data
    mock_resp.raise_for_status.return_value = None
    mock_client.__enter__.return_value.post.return_value = mock_resp
    return patch("app.services.payu_service.httpx.Client", return_value=mock_client)


def test_payu_checkout_session_creation(client, created_order):
    """Test creating a PayU Hosted Checkout session for an order."""
    order_id = created_order["order_id"]
    res = client.post(f"/api/payments/{order_id}/checkout?provider=payu")
    assert res.status_code == 200
    data = res.json()

    assert data["provider"] == "payu"
    assert data["mode"] == "test"
    assert data["checkout_url"] == "https://test.payu.in/_payment"
    assert data["payment_session_id"] is not None
    assert data["payment_session_id"].startswith("TXN-PAYU-")

    params = data.get("payu_params")
    assert params is not None
    assert params["key"] == "TH9CFX"
    assert params["txnid"] == data["payment_session_id"]
    assert float(params["amount"]) == pytest.approx(float(created_order["total_amount"]))
    assert params["udf1"] == created_order["id"]
    assert params["udf2"] == created_order["order_number"]
    assert params["action"] == "https://test.payu.in/_payment"
    assert params["hash"] is not None
    assert len(params["hash"]) == 128  # SHA-512 hex is 128 characters

    # Security check: Never expose merchant salt in frontend response
    assert "salt" not in data
    assert "PAYU_MERCHANT_SALT" not in data
    assert settings.PAYU_MERCHANT_SALT not in json.dumps(data)


def test_payu_successful_payment_callback_and_verification(client, created_order, db_session):
    """
    Test the full PayU Hosted Checkout success flow:
    1. Outbound request payload generated.
    2. Inbound callback received with valid hash.
    3. Backend independently verifies with PayU Postservice API.
    4. Only verified payment is marked PAID and CONFIRMED.
    """
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    assert checkout_res.status_code == 200
    payu_params = checkout_res.json()["payu_params"]
    txnid = payu_params["txnid"]
    amount = payu_params["amount"]

    mihpayid = "403993715526978130"
    bank_ref = "UPI202611020001"

    res_hash = generate_payu_response_hash(
        status="success",
        txnid=txnid,
        amount=amount,
        productinfo=payu_params["productinfo"],
        firstname=payu_params["firstname"],
        email=payu_params["email"],
        udf1=payu_params["udf1"],
        udf2=payu_params["udf2"],
    )

    callback_data = {
        "status": "success",
        "txnid": txnid,
        "amount": amount,
        "productinfo": payu_params["productinfo"],
        "firstname": payu_params["firstname"],
        "email": payu_params["email"],
        "udf1": payu_params["udf1"],
        "udf2": payu_params["udf2"],
        "mihpayid": mihpayid,
        "bank_ref_num": bank_ref,
        "mode": "UPI",
        "unmappedstatus": "captured",
        "key": "TH9CFX",
        "hash": res_hash,
    }

    # Mock independent verification with PayU Postservice API
    mock_verification_response = {
        "status": 1,
        "msg": "1 Transactions found",
        "transaction_details": {
            txnid: {
                "mihpayid": mihpayid,
                "status": "success",
                "amt": amount,
                "txnid": txnid,
                "mode": "UPI",
                "unmappedstatus": "captured",
                "bank_ref_num": bank_ref,
            }
        },
    }

    with mock_payu_service_post(mock_verification_response):
        # Send callback request with Accept: application/json
        res = client.post(
            "/api/payments/payu/response",
            data=callback_data,
            headers={"Accept": "application/json"},
        )
        assert res.status_code == 200
        res_json = res.json()
        assert res_json["status"] == "success"
        assert res_json["payment_status"] == "PAID"
        assert res_json["order_status"] == "CONFIRMED"
        assert res_json["payment_reference"] == mihpayid

    # Check database state
    db_order = db_session.query(Order).filter(Order.id == created_order["id"]).first()
    assert db_order.status == OrderStatus.CONFIRMED.value
    assert db_order.payment_status == "SUCCESS"
    assert db_order.is_paid is True
    assert db_order.payment_reference == mihpayid
    assert db_order.payment_session_id == txnid
    assert db_order.payment_timestamp is not None


def test_payu_failed_payment_callback(client, created_order, db_session):
    """Test that a failed payment callback marks order FAILED and NOT confirmed."""
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    payu_params = checkout_res.json()["payu_params"]
    txnid = payu_params["txnid"]
    amount = payu_params["amount"]

    res_hash = generate_payu_response_hash(
        status="failure",
        txnid=txnid,
        amount=amount,
        productinfo=payu_params["productinfo"],
        firstname=payu_params["firstname"],
        email=payu_params["email"],
        udf1=payu_params["udf1"],
        udf2=payu_params["udf2"],
    )

    callback_data = {
        "status": "failure",
        "txnid": txnid,
        "amount": amount,
        "productinfo": payu_params["productinfo"],
        "firstname": payu_params["firstname"],
        "email": payu_params["email"],
        "udf1": payu_params["udf1"],
        "udf2": payu_params["udf2"],
        "mihpayid": "403993715526978131",
        "mode": "UPI",
        "unmappedstatus": "failed",
        "error_Message": "Bank declined payment",
        "key": "TH9CFX",
        "hash": res_hash,
    }

    res = client.post(
        "/api/payments/payu/response",
        data=callback_data,
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 200
    res_json = res.json()
    assert res_json["status"] == "failed"
    assert res_json["payment_status"] == "FAILED"
    assert res_json["order_status"] == OrderStatus.FAILED.value

    # Verify order in DB
    db_order = db_session.query(Order).filter(Order.id == created_order["id"]).first()
    assert db_order.status == OrderStatus.FAILED.value
    assert db_order.payment_status == "FAILED"
    assert db_order.is_paid is False


def test_payu_cancelled_payment_callback(client, created_order, db_session):
    """Test that a user-cancelled payment callback marks order CANCELLED."""
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    payu_params = checkout_res.json()["payu_params"]
    txnid = payu_params["txnid"]
    amount = payu_params["amount"]

    res_hash = generate_payu_response_hash(
        status="failure",
        txnid=txnid,
        amount=amount,
        productinfo=payu_params["productinfo"],
        firstname=payu_params["firstname"],
        email=payu_params["email"],
        udf1=payu_params["udf1"],
        udf2=payu_params["udf2"],
    )

    callback_data = {
        "status": "failure",
        "txnid": txnid,
        "amount": amount,
        "productinfo": payu_params["productinfo"],
        "firstname": payu_params["firstname"],
        "email": payu_params["email"],
        "udf1": payu_params["udf1"],
        "udf2": payu_params["udf2"],
        "mode": "UPI",
        "unmappedstatus": "userCancelled",
        "error_Message": "Transaction cancelled by user",
        "key": "TH9CFX",
        "hash": res_hash,
    }

    res = client.post(
        "/api/payments/payu/response",
        data=callback_data,
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 200
    res_json = res.json()
    assert res_json["status"] == "failed"
    assert res_json["payment_status"] == "CANCELLED"
    assert res_json["order_status"] == OrderStatus.CANCELLED.value

    db_order = db_session.query(Order).filter(Order.id == created_order["id"]).first()
    assert db_order.status == OrderStatus.CANCELLED.value
    assert db_order.payment_status == "CANCELLED"
    assert db_order.is_paid is False


def test_payu_invalid_hash_rejected(client, created_order, db_session):
    """Test that a tampered or invalid PayU response hash is rejected with HTTP 400."""
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    payu_params = checkout_res.json()["payu_params"]
    txnid = payu_params["txnid"]

    fake_hash = "abcdef1234567890" * 8  # 128 characters invalid hash

    callback_data = {
        "status": "success",
        "txnid": txnid,
        "amount": payu_params["amount"],
        "productinfo": payu_params["productinfo"],
        "firstname": payu_params["firstname"],
        "email": payu_params["email"],
        "udf1": payu_params["udf1"],
        "udf2": payu_params["udf2"],
        "mihpayid": "403993715526978999",
        "key": "TH9CFX",
        "hash": fake_hash,
    }

    res = client.post("/api/payments/payu/response", data=callback_data)
    assert res.status_code == 400
    assert "Invalid PayU response hash signature" in res.json()["detail"]

    # Order must NOT be marked paid
    db_order = db_session.query(Order).filter(Order.id == created_order["id"]).first()
    assert db_order.status != OrderStatus.CONFIRMED.value
    assert db_order.payment_status != "SUCCESS"
    assert db_order.is_paid is False


def test_payu_failed_independent_verification_rejects_payment(client, created_order, db_session):
    """
    Test Step 8: Even if the response hash is technically valid,
    if PayU Postservice API independently returns unconfirmed/failure,
    the backend must reject the payment and NOT mark the order PAID.
    """
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    payu_params = checkout_res.json()["payu_params"]
    txnid = payu_params["txnid"]
    amount = payu_params["amount"]

    res_hash = generate_payu_response_hash(
        status="success",
        txnid=txnid,
        amount=amount,
        productinfo=payu_params["productinfo"],
        firstname=payu_params["firstname"],
        email=payu_params["email"],
        udf1=payu_params["udf1"],
        udf2=payu_params["udf2"],
    )

    callback_data = {
        "status": "success",
        "txnid": txnid,
        "amount": amount,
        "productinfo": payu_params["productinfo"],
        "firstname": payu_params["firstname"],
        "email": payu_params["email"],
        "udf1": payu_params["udf1"],
        "udf2": payu_params["udf2"],
        "mihpayid": "403993715526978130",
        "key": "TH9CFX",
        "hash": res_hash,
    }

    # Simulate PayU postservice API reporting transaction not found or failed
    mock_failed_verification = {
        "status": 0,
        "msg": "No Transaction Found",
        "transaction_details": {},
    }

    with mock_payu_service_post(mock_failed_verification):
        res = client.post("/api/payments/payu/response", data=callback_data)
        assert res.status_code == 400
        assert "Payment independent verification failed with PayU" in res.json()["detail"]

    db_order = db_session.query(Order).filter(Order.id == created_order["id"]).first()
    assert db_order.status != OrderStatus.CONFIRMED.value
    assert db_order.payment_status == "VERIFICATION_FAILED"
    assert db_order.is_paid is False


def test_payu_duplicate_callback_idempotency(client, created_order, db_session):
    """Test that duplicate callback submissions are idempotent and do not create duplicate orders."""
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    payu_params = checkout_res.json()["payu_params"]
    txnid = payu_params["txnid"]
    amount = payu_params["amount"]
    mihpayid = "403993715526978130"

    res_hash = generate_payu_response_hash(
        status="success",
        txnid=txnid,
        amount=amount,
        productinfo=payu_params["productinfo"],
        firstname=payu_params["firstname"],
        email=payu_params["email"],
        udf1=payu_params["udf1"],
        udf2=payu_params["udf2"],
    )

    callback_data = {
        "status": "success",
        "txnid": txnid,
        "amount": amount,
        "productinfo": payu_params["productinfo"],
        "firstname": payu_params["firstname"],
        "email": payu_params["email"],
        "udf1": payu_params["udf1"],
        "udf2": payu_params["udf2"],
        "mihpayid": mihpayid,
        "key": "TH9CFX",
        "hash": res_hash,
    }

    mock_verification = {
        "status": 1,
        "msg": "1 Transactions found",
        "transaction_details": {
            txnid: {
                "mihpayid": mihpayid,
                "status": "success",
                "amt": amount,
                "txnid": txnid,
            }
        },
    }

    with mock_payu_service_post(mock_verification):
        # First callback -> confirms order
        res1 = client.post("/api/payments/payu/response", data=callback_data, headers={"Accept": "application/json"})
        assert res1.status_code == 200
        assert res1.json()["payment_status"] == "PAID"

        # Duplicate callback -> returns idempotent success
        res2 = client.post("/api/payments/payu/response", data=callback_data, headers={"Accept": "application/json"})
        assert res2.status_code == 200
        assert res2.json()["payment_status"] == "PAID"
        assert res2.json()["message"] == "Order already paid."

    # Verify no duplicate orders created in database
    orders_matching = db_session.query(Order).filter(Order.id == created_order["id"]).all()
    assert len(orders_matching) == 1


def test_payu_payment_status_polling(client, created_order, db_session):
    """Test polling /api/payments/{order_id}/status automatically verifies PayU transaction."""
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    txnid = checkout_res.json()["payu_params"]["txnid"]
    mihpayid = "403993715526978555"

    mock_verification = {
        "status": 1,
        "msg": "1 Transactions found",
        "transaction_details": {
            txnid: {
                "mihpayid": mihpayid,
                "status": "success",
                "amt": str(created_order["total_amount"]),
                "txnid": txnid,
            }
        },
    }

    with mock_payu_service_post(mock_verification):
        status_res = client.get(f"/api/payments/{order_id}/status")
        assert status_res.status_code == 200
        data = status_res.json()
        assert data["is_paid"] is True
        assert data["payment_status"] == "PAID"
        assert data["payment_reference"] == mihpayid


def test_payu_confirmed_order_appears_on_tablet_dashboard(client, created_order, db_session):
    """
    Test Step 10: After PayU payment verification, the confirmed order
    becomes immediately available through the existing tablet order API.
    """
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    payu_params = checkout_res.json()["payu_params"]
    txnid = payu_params["txnid"]
    amount = payu_params["amount"]
    mihpayid = "403993715526978999"

    res_hash = generate_payu_response_hash(
        status="success",
        txnid=txnid,
        amount=amount,
        productinfo=payu_params["productinfo"],
        firstname=payu_params["firstname"],
        email=payu_params["email"],
        udf1=payu_params["udf1"],
        udf2=payu_params["udf2"],
    )

    callback_data = {
        "status": "success",
        "txnid": txnid,
        "amount": amount,
        "productinfo": payu_params["productinfo"],
        "firstname": payu_params["firstname"],
        "email": payu_params["email"],
        "udf1": payu_params["udf1"],
        "udf2": payu_params["udf2"],
        "mihpayid": mihpayid,
        "key": "TH9CFX",
        "hash": res_hash,
    }

    mock_verification = {
        "status": 1,
        "msg": "1 Transactions found",
        "transaction_details": {
            txnid: {
                "mihpayid": mihpayid,
                "status": "success",
                "amt": amount,
                "txnid": txnid,
            }
        },
    }

    with mock_payu_service_post(mock_verification):
        confirm_res = client.post("/api/payments/payu/response", data=callback_data, headers={"Accept": "application/json"})
        assert confirm_res.status_code == 200

    # Query tablet orders API
    tablet_res = client.get("/api/orders")
    assert tablet_res.status_code == 200
    orders_list = tablet_res.json()

    # Find the order
    matching = [o for o in orders_list if o["id"] == created_order["id"] or o["order_number"] == order_id]
    assert len(matching) == 1
    target = matching[0]

    # Must be CONFIRMED and marked PAID for tablet kiosk
    assert target["status"] in ("CONFIRMED", "PAID")
    assert target["payment_status"] in ("PAID", "SUCCESS")
    assert target["is_paid"] is True
    assert target["payment_reference"] == mihpayid


def test_missing_payu_credentials_handling(client, created_order, monkeypatch, db_session):
    """
    Requirements Check:
    When PayU credentials are not configured:
    - Non-payment health endpoint (/api/health) continues working.
    - PDF upload and order creation continue working.
    - Payment checkout returns HTTP 503 with clear configuration error.
    - Payment QR returns HTTP 503 with clear configuration error.
    - Does NOT crash the backend.
    - Does NOT generate fake payment success.
    - Does NOT mark order as PAID.
    - Does NOT bypass payment verification.
    """
    # Unset PayU credentials
    monkeypatch.setattr(settings, "PAYU_MERCHANT_KEY", "")
    monkeypatch.setattr(settings, "PAYU_MERCHANT_SALT", "")

    # 1. Health check continues working
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] in ("ok", "healthy")

    # 2. File upload continues working
    pdf_bytes = create_mock_pdf_bytes(page_count=1)
    upload_res = client.post(
        "/api/files/upload",
        files={"file": ("unconf_test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 201

    # 3. Order creation continues working
    order_id = created_order["order_id"]
    get_order_res = client.get(f"/api/orders/{order_id}")
    assert get_order_res.status_code == 200
    assert get_order_res.json()["payment_status"] == "PENDING"
    assert get_order_res.json()["is_paid"] is False

    # 4. Checkout returns clear HTTP 503 configuration error
    checkout_res = client.post(f"/api/payments/{order_id}/checkout?provider=payu")
    assert checkout_res.status_code == 503
    assert "PAYU_MERCHANT_KEY" in checkout_res.json()["detail"]
    assert "PAYU_MERCHANT_SALT" in checkout_res.json()["detail"]

    # 5. QR generation returns clear HTTP 503 configuration error
    qr_res = client.post(f"/api/payments/{order_id}/qr")
    assert qr_res.status_code == 503
    assert "PayU payment gateway is not configured" in qr_res.json()["detail"]

    # 6. Verification endpoint rejects because credentials are missing
    verify_res = client.post(f"/api/payments/{order_id}/verify-payu", json={"txnid": "test"})
    assert verify_res.status_code == 503

    # 7. Callback endpoint rejects because credentials are missing
    callback_res = client.post("/api/payments/payu/response", data={"txnid": "test"})
    assert callback_res.status_code == 503

    # 8. Order remains UNPAID
    db_order = db_session.query(Order).filter(Order.id == created_order["id"]).first()
    assert db_order.status != OrderStatus.CONFIRMED.value
    assert db_order.payment_status != "PAID"
    assert db_order.is_paid is False


def test_payu_amount_mismatch_rejected(client, created_order, db_session):
    """Security check: PayU callback with wrong payment amount must be rejected."""
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    payu_params = checkout_res.json()["payu_params"]
    txnid = payu_params["txnid"]
    wrong_amount = "9999.00"

    res_hash = generate_payu_response_hash(
        status="success",
        txnid=txnid,
        amount=wrong_amount,
        productinfo=payu_params["productinfo"],
        firstname=payu_params["firstname"],
        email=payu_params["email"],
        udf1=payu_params["udf1"],
        udf2=payu_params["udf2"],
    )

    callback_data = {
        "status": "success",
        "txnid": txnid,
        "amount": wrong_amount,
        "productinfo": payu_params["productinfo"],
        "firstname": payu_params["firstname"],
        "email": payu_params["email"],
        "udf1": payu_params["udf1"],
        "udf2": payu_params["udf2"],
        "mihpayid": "403993715526978130",
        "key": "TH9CFX",
        "hash": res_hash,
    }

    res = client.post("/api/payments/payu/response", data=callback_data)
    assert res.status_code == 400
    assert "amount mismatch" in res.json()["detail"].lower()

    # Order must NOT be marked paid
    db_order = db_session.query(Order).filter(Order.id == created_order["id"]).first()
    assert db_order.is_paid is False
    assert db_order.status != OrderStatus.CONFIRMED.value
