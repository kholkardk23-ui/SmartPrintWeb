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
from app.models import Order, OrderStatus, PaymentTransaction
from app.services import payu_service


TEST_PAYU_KEY = "MOCK_PAYU_KEY"
TEST_PAYU_SALT = "mock_payu_test_salt_secret_32bytes"


@pytest.fixture(autouse=True)
def force_payu_provider(monkeypatch):
    """Ensure PayU is the active payment provider for this test suite."""
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "payu")
    monkeypatch.setattr(settings, "PAYU_MODE", "test")
    monkeypatch.setattr(settings, "PAYU_MERCHANT_KEY", TEST_PAYU_KEY)
    monkeypatch.setattr(settings, "PAYU_MERCHANT_SALT", TEST_PAYU_SALT)
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
    salt: str = TEST_PAYU_SALT,
    key: str = TEST_PAYU_KEY,
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


MOCK_PAYU_INTENT_RESPONSE = {
    "status": 1,
    "result": {
        "intentURIData": "upi://pay?pa=smartprint@payu&pn=SmartPrint&tr=TXN-PAYU-TEST&am=18.00&cu=INR",
        "merchantVpa": "smartprint@payu",
        "merchantName": "SmartPrint",
        "paymentId": "MOCK-PAYU-PID-12345",
    },
}


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
    assert params["key"] == TEST_PAYU_KEY
    assert params["txnid"] == data["payment_session_id"]
    assert float(params["amount"]) == pytest.approx(float(created_order["total_amount"]))
    assert params["udf1"] == created_order["id"]
    assert params["udf2"] == created_order["order_number"]
    assert params["action"] == "https://test.payu.in/_payment"
    assert params["hash"] is not None
    assert len(params["hash"]) == 128  # SHA-512 hex is 128 characters

    # Gateway-level UPI-only enforcement parameters
    assert params["enforce_paymethod"] == "upi"
    assert params["drop_category"] == "CC|DC|NB|EMI|CASH|BNPL|REWARD"
    assert params["pg"] == "UPI"
    assert params["bankcode"] == "UPI"

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
        "key": TEST_PAYU_KEY,
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


def test_payu_rejects_non_upi_payment_mode(client, created_order, db_session):
    """
    Test that if a payment is processed via Credit Card, Debit Card, Net Banking,
    or other non-UPI mode, it is rejected under the UPI-only policy.
    """
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    assert checkout_res.status_code == 200
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
        "bank_ref_num": "CC-AUTH-12345",
        "mode": "CC",  # Non-UPI mode: Credit Card
        "unmappedstatus": "captured",
        "key": TEST_PAYU_KEY,
        "hash": res_hash,
    }

    mock_verification_response = {
        "status": 1,
        "msg": "1 Transactions found",
        "transaction_details": {
            txnid: {
                "mihpayid": mihpayid,
                "status": "success",
                "amt": amount,
                "txnid": txnid,
                "mode": "CC",
            }
        },
    }

    with mock_payu_service_post(mock_verification_response):
        res = client.post(
            "/api/payments/payu/response",
            data=callback_data,
            headers={"Accept": "application/json"},
        )
        assert res.status_code == 400
        assert "only accepts UPI payments" in res.json()["detail"]

    # Ensure order is NOT confirmed
    db_order = db_session.query(Order).filter(Order.id == created_order["id"]).first()
    assert db_order.status != OrderStatus.CONFIRMED.value
    assert db_order.is_paid is not True
    assert db_order.payment_status == "NON_UPI_REJECTED"


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
        "key": TEST_PAYU_KEY,
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
        "key": TEST_PAYU_KEY,
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
        "key": TEST_PAYU_KEY,
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
        "key": TEST_PAYU_KEY,
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
        "key": TEST_PAYU_KEY,
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
        "key": TEST_PAYU_KEY,
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
        "key": TEST_PAYU_KEY,
        "hash": res_hash,
    }

    res = client.post("/api/payments/payu/response", data=callback_data)
    assert res.status_code == 400
    assert "amount mismatch" in res.json()["detail"].lower()

    # Order must NOT be marked paid
    db_order = db_session.query(Order).filter(Order.id == created_order["id"]).first()
    assert db_order.is_paid is False
    assert db_order.status != OrderStatus.CONFIRMED.value


def test_payment_transaction_table_recording(client, created_order, db_session):
    """Test that PaymentTransaction records are created and updated throughout lifecycle."""
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    assert checkout_res.status_code == 200
    txnid = checkout_res.json()["payment_session_id"]

    # Verify transaction record exists with status INITIATED
    txn = db_session.query(PaymentTransaction).filter(PaymentTransaction.txnid == txnid).first()
    assert txn is not None
    assert txn.order_id == created_order["id"]
    assert float(txn.amount) == pytest.approx(float(created_order["total_amount"]))
    assert txn.payment_gateway == "PAYU"
    assert txn.payment_status == "INITIATED"

    # Simulate PayU callback
    payu_params = checkout_res.json()["payu_params"]
    amount = payu_params["amount"]
    mihpayid = "998877665544332211"
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
        "mode": "UPI",
        "key": TEST_PAYU_KEY,
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
                "mode": "UPI",
            }
        },
    }
    with mock_payu_service_post(mock_verification):
        res = client.post("/api/payments/payu/response", data=callback_data, headers={"Accept": "application/json"})
        assert res.status_code == 200

    # Verify transaction record updated to SUCCESS
    db_session.refresh(txn)
    assert txn.payment_status == "SUCCESS"
    assert txn.mihpayid == mihpayid


def test_payu_checkout_redirect_endpoint(client, created_order, db_session):
    """Test the GET /{order_id}/payu-checkout endpoint for tablet/mobile redirect."""
    order_id = created_order["order_id"]
    res = client.get(f"/api/payments/{order_id}/payu-checkout")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Redirecting to PayU" in res.text
    assert "payuForm" in res.text
    assert created_order["order_number"] in res.text
    # Verify gateway-level UPI restriction parameters are submitted in the HTML form
    assert 'name="enforce_paymethod" value="upi"' in res.text
    assert 'name="drop_category" value="CC|DC|NB|EMI|CASH|BNPL|REWARD"' in res.text
    assert 'name="pg" value="UPI"' in res.text
    assert 'name="bankcode" value="UPI"' in res.text


def test_payu_production_mode_urls(monkeypatch):
    """Verify that LIVE mode strictly selects PayU production endpoints."""
    monkeypatch.setattr(settings, "PAYU_MODE", "LIVE")
    assert payu_service.get_payu_payment_url() == "https://secure.payu.in/_payment"
    assert payu_service.get_payu_verify_url() == "https://info.payu.in/merchant/postservice.php?form=2"


def test_payu_smart_intent_checkout(client, created_order):
    """Test creating a PayU Smart Intent checkout session with all 5 UPI app options."""
    order_id = created_order["order_id"]
    with mock_payu_service_post(MOCK_PAYU_INTENT_RESPONSE):
        res = client.post(f"/api/payments/{order_id}/checkout?provider=payu")
    assert res.status_code == 200
    data = res.json()

    assert data["provider"] == "payu"
    assert data["payment_session_id"] is not None
    assert data["payment_session_id"].startswith("TXN-PAYU-")
    assert data["qr_type"] == "payu_smart_intent"

    # Verify Smart Intent apps structure
    upi_apps = data.get("upi_apps")
    assert upi_apps is not None
    assert "phonepe" in upi_apps
    assert "googlepay" in upi_apps
    assert "paytm" in upi_apps
    assert "bhim" in upi_apps
    assert "genericintent" in upi_apps

    # Verify PhonePe intent details
    phonepe = upi_apps["phonepe"]
    assert phonepe["name"] == "PhonePe"
    assert phonepe["package_name"] == "com.phonepe.app"
    assert "com.phonepe.app" in phonepe["android_intent"]
    assert "phonepe://" in phonepe["ios_scheme"]

    # Verify Google Pay intent details
    gpay = upi_apps["googlepay"]
    assert gpay["name"] == "Google Pay"
    assert gpay["package_name"] == "com.google.android.apps.nbu.paisa.user"
    assert "com.google.android.apps.nbu.paisa.user" in gpay["android_intent"]
    assert "gpay://" in gpay["ios_scheme"]

    # Verify Paytm intent details
    paytm = upi_apps["paytm"]
    assert paytm["name"] == "Paytm"
    assert paytm["package_name"] == "net.one97.paytm"
    assert "net.one97.paytm" in paytm["android_intent"]
    assert "paytm://" in paytm["ios_scheme"]

    # Verify BHIM intent details
    bhim = upi_apps["bhim"]
    assert bhim["name"] == "BHIM"
    assert bhim["package_name"] == "in.org.npci.upiapp"
    assert "in.org.npci.upiapp" in bhim["android_intent"]

    # Verify Generic intent chooser
    generic = upi_apps["genericintent"]
    assert generic["name"] == "Other UPI Apps"
    assert "scheme=upi" in generic["android_intent"]

    # Security check: Never expose merchant salt in frontend response
    assert "salt" not in data
    assert "PAYU_MERCHANT_SALT" not in data
    assert settings.PAYU_MERCHANT_SALT not in json.dumps(data)


def test_payu_specific_app_intent_endpoint(client, created_order):
    """Test POST /{order_id}/payu-intent endpoint for specific apps."""
    order_id = created_order["order_id"]

    with mock_payu_service_post(MOCK_PAYU_INTENT_RESPONSE):
        for app in ("phonepe", "googlepay", "paytm", "bhim", "genericintent"):
            res = client.post(f"/api/payments/{order_id}/payu-intent?app={app}")
            assert res.status_code == 200
            intent = res.json()
            assert intent["success"] is True
            assert intent["selected_app"] == app
            assert intent["intent_uri_data"] is not None
            assert intent["universal_upi_uri"].startswith("upi://pay?")
            assert app in intent["apps"]


def test_payu_tablet_qr_endpoint(client, created_order):
    """Test /{order_id}/qr endpoint with PayU Smart Intent."""
    order_id = created_order["order_id"]
    res = client.post(f"/api/payments/{order_id}/qr")
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "payu"
    assert data["payment_session_id"] is not None
    assert data["qr_data"] is not None
    assert "PayU" in data["message"]


def test_unique_txnid_generated_on_retry(client, created_order, db_session):
    """Confirm unique transaction ID is generated for each payment attempt while preserving the order."""
    order_id = created_order["order_id"]

    # First attempt
    res1 = client.post(f"/api/payments/{order_id}/checkout")
    assert res1.status_code == 200
    txnid1 = res1.json()["payment_session_id"]

    # Second attempt (e.g. customer retries payment)
    res2 = client.post(f"/api/payments/{order_id}/checkout")
    assert res2.status_code == 200
    txnid2 = res2.json()["payment_session_id"]

    assert txnid1 != txnid2
    assert txnid1.startswith("TXN-PAYU-")
    assert txnid2.startswith("TXN-PAYU-")

    # Order must remain single and preserved
    order = db_session.query(Order).filter((Order.id == created_order["id"]) | (Order.order_number == order_id)).first()
    assert order is not None

    # Both transaction attempts recorded in payment_transactions table
    txns = db_session.query(PaymentTransaction).filter(PaymentTransaction.order_id == order.id).all()
    assert len(txns) >= 2


def test_pending_and_failed_payment_does_not_mark_order_paid(client, created_order, db_session):
    """Confirm pending and failed payments do not mark order as paid."""
    order_id = created_order["order_id"]
    checkout_res = client.post(f"/api/payments/{order_id}/checkout")
    assert checkout_res.status_code == 200
    txnid = checkout_res.json()["payment_session_id"]
    amount = checkout_res.json()["payu_params"]["amount"]

    # Test pending payment: order remains unpaid
    status_res = client.get(f"/api/payments/{order_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["is_paid"] is False
    assert status_res.json()["status"] == "PAYMENT_PENDING"

    # Test failed callback
    res_hash = generate_payu_response_hash(
        status="failure",
        txnid=txnid,
        amount=amount,
        productinfo=checkout_res.json()["payu_params"]["productinfo"],
        firstname=checkout_res.json()["payu_params"]["firstname"],
        email=checkout_res.json()["payu_params"]["email"],
        udf1=checkout_res.json()["payu_params"]["udf1"],
        udf2=checkout_res.json()["payu_params"]["udf2"],
    )
    fail_data = {
        "status": "failure",
        "txnid": txnid,
        "amount": amount,
        "productinfo": checkout_res.json()["payu_params"]["productinfo"],
        "firstname": checkout_res.json()["payu_params"]["firstname"],
        "email": checkout_res.json()["payu_params"]["email"],
        "udf1": checkout_res.json()["payu_params"]["udf1"],
        "udf2": checkout_res.json()["payu_params"]["udf2"],
        "key": TEST_PAYU_KEY,
        "hash": res_hash,
        "error_Message": "Bank declined transaction",
    }
    fail_res = client.post("/api/payments/payu/response", data=fail_data, headers={"Accept": "application/json"})
    assert fail_res.status_code == 200
    assert fail_res.json()["status"] == "failed"

    # Order must NOT be marked paid
    db_order = db_session.query(Order).filter((Order.id == created_order["id"]) | (Order.order_number == order_id)).first()
    assert db_order.status in ("FAILED", "PAYMENT_PENDING")
    assert getattr(db_order, "is_paid", False) is False


def test_payu_merchant_key_mismatch_rejected(client, created_order):
    """Security check: PayU callback with mismatched merchant key must be rejected."""
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
        key="WRONG_MERCHANT_KEY",
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
        "key": "WRONG_MERCHANT_KEY",
        "hash": res_hash,
    }
    res = client.post("/api/payments/payu/response", data=callback_data)
    assert res.status_code == 400
    assert "merchant key" in res.json()["detail"].lower()


# ============================================================
# FLOW 2 – TABLET SCANNER PAYMENT TESTS
# ============================================================

def test_flow_2_tablet_qr_payment_success(client, created_order, db_session):
    """
    Test Flow 2: Tablet Scanner Payment End-to-End.
    1. Order created in CREATED state.
    2. Tablet fetches QR code via /{order_id}/qr.
    3. Checks valid UPI URI and PayU transaction tracking.
    4. Customer scans QR with PhonePe / GPay and pays.
    5. PayU callback received with hash and verified via PayU Verify Payment API.
    6. PaymentTransaction marked SUCCESS, Order marked CONFIRMED / PAID.
    7. Order immediately accessible on tablet dashboard.
    """
    order_id = created_order["order_id"]
    db_order = db_session.query(Order).filter((Order.id == created_order["id"]) | (Order.order_number == order_id)).first()
    assert db_order is not None

    # Step 2: Tablet calls /{order_id}/qr to display payment QR
    with mock_payu_service_post(MOCK_PAYU_INTENT_RESPONSE):
        qr_res = client.post(f"/api/payments/{order_id}/qr")
    assert qr_res.status_code == 200
    qr_data = qr_res.json()

    assert qr_data["provider"] == "payu"
    assert qr_data["payment_session_id"] is not None
    assert qr_data["payment_session_id"].startswith("TXN-PAYU-")
    assert qr_data["upi_uri"] is not None
    assert qr_data["upi_uri"].startswith("upi://pay?")
    assert qr_data["qr_data"].startswith("upi://pay?")
    assert qr_data["qr_type"] in ("payu_smart_intent", "payu_dynamic_upi_qr")

    txnid = qr_data["payment_session_id"]
    amount = f"{float(created_order['total_amount']):.2f}"

    # Step 3: Transaction attempt recorded in payment_transactions
    txn = db_session.query(PaymentTransaction).filter(PaymentTransaction.txnid == txnid).first()
    assert txn is not None
    assert txn.order_id == db_order.id
    assert txn.payment_status == "INITIATED"

    # Step 4 & 5: PayU callback for tablet QR payment
    productinfo = f"SmartPrint Order {db_order.order_number or db_order.id}"
    res_hash = generate_payu_response_hash(
        status="success",
        txnid=txnid,
        amount=amount,
        productinfo=productinfo,
        firstname="Customer",
        email="customer@smartprint.local",
        udf1=str(db_order.id),
        udf2=str(db_order.order_number),
    )
    callback_data = {
        "status": "success",
        "txnid": txnid,
        "amount": amount,
        "productinfo": productinfo,
        "firstname": "Customer",
        "email": "customer@smartprint.local",
        "udf1": str(db_order.id),
        "udf2": str(db_order.order_number),
        "key": TEST_PAYU_KEY,
        "hash": res_hash,
        "mihpayid": "PAYU_TAB_MIH_9999",
        "bank_ref_num": "BANK_TAB_REF_8888",
        "mode": "UPI",
    }

    mock_verify = {
        "verified": True,
        "status": "success",
        "transaction": {"status": "success", "amt": amount, "mihpayid": "PAYU_TAB_MIH_9999"},
        "mihpayid": "PAYU_TAB_MIH_9999",
        "amount": amount,
        "mode": "UPI",
    }

    with patch.object(payu_service, "verify_payment_with_payu", return_value=mock_verify):
        cb_res = client.post(
            "/api/payments/payu/response",
            data=callback_data,
            headers={"Accept": "application/json"},
        )
        assert cb_res.status_code == 200
        res_json = cb_res.json()
        assert res_json["status"] == "success"
        assert res_json["payment_status"] == "PAID"
        assert res_json["order_status"] in ("CONFIRMED", "PAID")

    # Step 6: Database verification
    db_session.expire_all()
    updated_order = db_session.query(Order).filter(Order.id == db_order.id).first()
    assert updated_order.status in ("CONFIRMED", "PAID")
    assert updated_order.payment_status in ("PAID", "SUCCESS")
    assert updated_order.is_paid is True
    assert updated_order.payment_reference == "PAYU_TAB_MIH_9999"

    updated_txn = db_session.query(PaymentTransaction).filter(PaymentTransaction.txnid == txnid).first()
    assert updated_txn.payment_status == "SUCCESS"
    assert updated_txn.mihpayid == "PAYU_TAB_MIH_9999"

    # Step 7: Tablet polling reflects confirmed order
    status_res = client.get(f"/api/payments/{order_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["is_paid"] is True
    assert status_res.json()["payment_status"] == "PAID"

    # Step 8: Order visible in latest confirmed orders for tablet
    latest_res = client.get("/api/orders/latest?confirmed_only=true")
    assert latest_res.status_code == 200
    assert latest_res.json()["order_number"] == db_order.order_number
    assert latest_res.json()["is_paid"] is True


def test_flow_2_tablet_qr_order_matching_by_txnid_alone(client, created_order, db_session):
    """
    Test Flow 2 robustness: Match order even when PayU callback lacks udf1 / udf2.
    The order is matched through PaymentTransaction table.
    """
    order_id = created_order["order_id"]
    db_order = db_session.query(Order).filter((Order.id == created_order["id"]) | (Order.order_number == order_id)).first()

    # Generate QR to initiate transaction
    qr_res = client.post(f"/api/payments/{order_id}/qr")
    txnid = qr_res.json()["payment_session_id"]
    amount = f"{float(created_order['total_amount']):.2f}"
    productinfo = f"SmartPrint Order {db_order.order_number or db_order.id}"

    # Callback with empty udf1 and udf2
    res_hash = generate_payu_response_hash(
        status="success",
        txnid=txnid,
        amount=amount,
        productinfo=productinfo,
        firstname="Customer",
        email="customer@smartprint.local",
        udf1="",
        udf2="",
    )
    callback_data = {
        "status": "success",
        "txnid": txnid,
        "amount": amount,
        "productinfo": productinfo,
        "firstname": "Customer",
        "email": "customer@smartprint.local",
        "udf1": "",
        "udf2": "",
        "key": TEST_PAYU_KEY,
        "hash": res_hash,
        "mihpayid": "PAYU_NO_UDF_9999",
    }

    mock_verify = {
        "verified": True,
        "status": "success",
        "transaction": {"status": "success", "amt": amount},
        "mihpayid": "PAYU_NO_UDF_9999",
        "amount": amount,
        "mode": "UPI",
    }

    with patch.object(payu_service, "verify_payment_with_payu", return_value=mock_verify):
        cb_res = client.post(
            "/api/payments/payu/response",
            data=callback_data,
            headers={"Accept": "application/json"},
        )
        assert cb_res.status_code == 200
        assert cb_res.json()["status"] == "success"

    db_session.expire_all()
    updated_order = db_session.query(Order).filter(Order.id == db_order.id).first()
    assert updated_order.status in ("CONFIRMED", "PAID")
    assert updated_order.is_paid is True


def test_flow_2_tablet_qr_polling_verifies_payu_payment(client, created_order, db_session):
    """
    Test that tablet polling at /api/payments/{order_id}/status automatically
    verifies PayU payment if customer completes payment on phone.
    """
    order_id = created_order["order_id"]
    db_order = db_session.query(Order).filter((Order.id == created_order["id"]) | (Order.order_number == order_id)).first()

    qr_res = client.post(f"/api/payments/{order_id}/qr")
    txnid = qr_res.json()["payment_session_id"]
    amount = f"{float(created_order['total_amount']):.2f}"

    mock_verify = {
        "verified": True,
        "status": "success",
        "transaction": {"status": "success", "amt": amount},
        "mihpayid": "PAYU_POLL_VERIFIED_7777",
        "amount": amount,
        "mode": "UPI",
    }

    with patch.object(payu_service, "verify_payment_with_payu", return_value=mock_verify):
        status_res = client.get(f"/api/payments/{order_id}/status")
        assert status_res.status_code == 200
        data = status_res.json()
        assert data["is_paid"] is True
        assert data["payment_status"] == "PAID"
        assert data["payment_reference"] == "PAYU_POLL_VERIFIED_7777"

    db_session.expire_all()
    updated_order = db_session.query(Order).filter(Order.id == db_order.id).first()
    assert updated_order.is_paid is True
    assert updated_order.status in ("CONFIRMED", "PAID")


def test_payu_end_to_end_customer_to_tablet_flow(client, db_session):
    """
    End-to-End Verification of Phase 6 Requirements:
    1. Proceed to Pay creates a database order.
    2. Newly created order has PAYMENT_PENDING status.
    3. Tablet latest-order endpoint returns pending order.
    4. PayU initialization uses the existing order ID.
    5. Valid PayU success callback verifies payment.
    6. Verified payment updates the same order to PAID/CONFIRMED.
    7. Invalid hash cannot confirm payment.
    8. Failed payment does not confirm order.
    9. Duplicate callback does not duplicate orders.
    10. Tablet displays confirmed order after polling.
    """
    # 1. Proceed to Pay creates a database order
    pdf_bytes = create_mock_pdf_bytes(page_count=2)
    upload_res = client.post(
        "/api/files/upload",
        files={"file": ("report.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
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
    create_res = client.post("/api/orders", json=order_payload)
    assert create_res.status_code == 201
    order_data = create_res.json()
    order_uuid = order_data["id"]
    order_number = order_data["order_number"]

    # 2. Newly created order has PAYMENT_PENDING status
    assert order_data["status"] == "PAYMENT_PENDING"
    assert order_data["payment_status"] == "PENDING"
    assert order_data["is_paid"] is False

    # 3. Tablet latest-order endpoint returns pending order immediately
    tablet_latest = client.get("/api/orders/latest")
    assert tablet_latest.status_code == 200
    latest_data = tablet_latest.json()
    assert latest_data["order_number"] == order_number
    assert latest_data["status"] == "PAYMENT_PENDING"
    assert latest_data["is_paid"] is False

    # 4. PayU initialization uses the existing order ID
    checkout_res = client.get(f"/api/payments/{order_number}/payu-checkout")
    assert checkout_res.status_code == 200
    assert "Redirecting to PayU" in checkout_res.text
    assert f"Order {order_number}" in checkout_res.text

    # Verify transaction was recorded for this exact order
    db_order = db_session.query(Order).filter(Order.id == order_uuid).first()
    assert db_order.payment_session_id is not None
    txnid = db_order.payment_session_id
    assert txnid.startswith("TXN-PAYU-")

    amount = f"{float(order_data['total_amount']):.2f}"
    productinfo = f"SmartPrint Order {order_number}"

    # 7. Invalid hash cannot confirm payment
    invalid_hash_data = {
        "status": "success",
        "txnid": txnid,
        "amount": amount,
        "productinfo": productinfo,
        "firstname": "Customer",
        "email": "customer@smartprint.local",
        "udf1": order_uuid,
        "udf2": order_number,
        "key": TEST_PAYU_KEY,
        "hash": "tampered_bad_hash_signature",
        "mihpayid": "MIH_TAMPERED",
    }
    bad_hash_res = client.post(
        "/api/payments/payu/response",
        data=invalid_hash_data,
        headers={"Accept": "application/json"},
    )
    assert bad_hash_res.status_code == 400

    db_session.expire_all()
    check_order = db_session.query(Order).filter(Order.id == order_uuid).first()
    assert check_order.is_paid is False
    assert check_order.status == "PAYMENT_PENDING"

    # 8. Failed payment does not confirm order
    failed_hash = generate_payu_response_hash(
        status="failure",
        txnid=txnid,
        amount=amount,
        productinfo=productinfo,
        firstname="Customer",
        email="customer@smartprint.local",
        udf1=order_uuid,
        udf2=order_number,
    )
    failed_data = {
        "status": "failure",
        "txnid": txnid,
        "amount": amount,
        "productinfo": productinfo,
        "firstname": "Customer",
        "email": "customer@smartprint.local",
        "udf1": order_uuid,
        "udf2": order_number,
        "key": TEST_PAYU_KEY,
        "hash": failed_hash,
        "error_Message": "Bank declined transaction",
    }
    fail_res = client.post(
        "/api/payments/payu/response",
        data=failed_data,
        headers={"Accept": "application/json"},
    )
    assert fail_res.status_code == 200
    assert fail_res.json()["status"] == "failed"

    db_session.expire_all()
    check_order_fail = db_session.query(Order).filter(Order.id == order_uuid).first()
    assert check_order_fail.is_paid is False
    assert check_order_fail.status == "FAILED"

    # Reset order back to PAYMENT_PENDING for success test (simulating customer retry)
    check_order_fail.status = "PAYMENT_PENDING"
    check_order_fail.payment_status = "PENDING"
    db_session.commit()

    # 5. Valid PayU success callback verifies payment
    good_hash = generate_payu_response_hash(
        status="success",
        txnid=txnid,
        amount=amount,
        productinfo=productinfo,
        firstname="Customer",
        email="customer@smartprint.local",
        udf1=order_uuid,
        udf2=order_number,
    )
    success_data = {
        "status": "success",
        "txnid": txnid,
        "amount": amount,
        "productinfo": productinfo,
        "firstname": "Customer",
        "email": "customer@smartprint.local",
        "udf1": order_uuid,
        "udf2": order_number,
        "key": TEST_PAYU_KEY,
        "hash": good_hash,
        "mihpayid": "MIH_PAYU_E2E_8888",
        "bank_ref_num": "BANK_REF_8888",
    }
    mock_verify = {
        "verified": True,
        "status": "success",
        "transaction": {"status": "success", "amt": amount},
        "mihpayid": "MIH_PAYU_E2E_8888",
        "bank_ref_num": "BANK_REF_8888",
        "amount": amount,
        "mode": "UPI",
    }

    with patch.object(payu_service, "verify_payment_with_payu", return_value=mock_verify):
        success_res = client.post(
            "/api/payments/payu/response",
            data=success_data,
            headers={"Accept": "application/json"},
        )
        assert success_res.status_code == 200
        assert success_res.json()["status"] == "success"
        assert success_res.json()["payment_status"] == "PAID"

    # 6. Verified payment updates the same order to PAID/CONFIRMED
    db_session.expire_all()
    confirmed_order = db_session.query(Order).filter(Order.id == order_uuid).first()
    assert confirmed_order.is_paid is True
    assert confirmed_order.status in ("CONFIRMED", "PAID")
    assert confirmed_order.payment_reference == "MIH_PAYU_E2E_8888"

    # 9. Duplicate callback does not duplicate orders
    order_count_before = db_session.query(Order).count()
    with patch.object(payu_service, "verify_payment_with_payu", return_value=mock_verify):
        dup_res = client.post(
            "/api/payments/payu/response",
            data=success_data,
            headers={"Accept": "application/json"},
        )
        assert dup_res.status_code == 200
        assert dup_res.json()["status"] == "success"

    db_session.expire_all()
    order_count_after = db_session.query(Order).count()
    assert order_count_before == order_count_after

    # 10. Tablet displays confirmed order after polling
    tablet_poll = client.get("/api/orders/latest?confirmed_only=true")
    assert tablet_poll.status_code == 200
    tablet_order = tablet_poll.json()
    assert tablet_order["order_number"] == order_number
    assert tablet_order["status"] in ("CONFIRMED", "PAID")
    assert tablet_order["is_paid"] is True
    assert tablet_order["payment_reference"] == "MIH_PAYU_E2E_8888"


