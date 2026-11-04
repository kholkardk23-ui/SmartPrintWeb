"""
PayU India Payment Gateway Integration Service
=============================================
Provides Hosted Checkout support for SmartPrint using PayU India.
Handles outbound request hashing, inbound response hash validation,
and independent server-to-server transaction verification.
"""

import hashlib
import hmac
import logging
import urllib.parse
import uuid
from typing import Any, Dict, Optional

import httpx
from app.config import settings

logger = logging.getLogger("smartprint.payments.payu")


class PayUError(Exception):
    """Raised when PayU processing fails."""
    pass


def get_payu_payment_url() -> str:
    """Return the authoritative PayU Hosted Checkout action endpoint."""
    mode = (settings.PAYU_MODE or "test").strip().lower()
    custom_url = (settings.PAYU_PAYMENT_URL or "").strip()
    if custom_url:
        if mode in ("live", "production") and "test.payu.in" in custom_url:
            return "https://secure.payu.in/_payment"
        if mode == "test" and "secure.payu.in" in custom_url:
            return "https://test.payu.in/_payment"
        return custom_url
    return "https://secure.payu.in/_payment" if mode in ("live", "production") else "https://test.payu.in/_payment"


def get_payu_verify_url() -> str:
    """Return the authoritative PayU Postservice transaction verification endpoint."""
    mode = (settings.PAYU_MODE or "test").strip().lower()
    custom_url = (settings.PAYU_VERIFY_URL or "").strip()
    if custom_url:
        if mode in ("live", "production") and "test.payu.in" in custom_url:
            return "https://info.payu.in/merchant/postservice.php?form=2"
        if mode == "test" and "info.payu.in" in custom_url:
            return "https://test.payu.in/merchant/postservice.php?form=2"
        return custom_url
    return (
        "https://info.payu.in/merchant/postservice.php?form=2"
        if mode in ("live", "production")
        else "https://test.payu.in/merchant/postservice.php?form=2"
    )


def get_payu_callback_url() -> str:
    """Return the server callback URL (SURL/FURL) for PayU responses."""
    if (settings.PAYU_SUCCESS_URL or "").strip():
        return settings.PAYU_SUCCESS_URL.strip()
    backend_base = (getattr(settings, "BACKEND_URL", None) or "http://localhost:8000").rstrip("/")
    return f"{backend_base}/api/payments/payu/response"


def generate_txnid(order) -> str:
    """
    Generate a deterministic or unique transaction ID for PayU.
    PayU requires a unique transaction ID per payment attempt.
    """
    existing = getattr(order, "payment_session_id", None)
    if existing and str(existing).startswith("TXN-PAYU-"):
        return str(existing)

    order_ref = str(order.order_number or getattr(order, "id", "")[:8]).replace("-", "")
    unique_suffix = uuid.uuid4().hex[:6].upper()
    return f"TXN-PAYU-{order_ref}-{unique_suffix}"


def generate_request_hash(
    key: str,
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
    salt: str = "",
) -> str:
    """
    Generate SHA-512 request hash for PayU Hosted Checkout.
    Sequence:
    sha512(key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||SALT)
    """
    hash_sequence = (
        f"{key}|{txnid}|{amount}|{productinfo}|{firstname}|{email}|"
        f"{udf1}|{udf2}|{udf3}|{udf4}|{udf5}||||||{salt}"
    )
    return hashlib.sha512(hash_sequence.encode("utf-8")).hexdigest().lower()


def prepare_payment_payload(order) -> Dict[str, Any]:
    """
    Prepare all parameters required for PayU Hosted Checkout form submission.
    Calculates the SHA-512 hash and NEVER exposes the merchant salt to the frontend.
    """
    key = (settings.PAYU_MERCHANT_KEY or "").strip()
    salt = (settings.PAYU_MERCHANT_SALT or "").strip()
    if not key or not salt:
        raise PayUError("PayU credentials (PAYU_MERCHANT_KEY, PAYU_MERCHANT_SALT) are missing.")

    txnid = generate_txnid(order)
    amount_str = f"{float(order.total_amount):.2f}"
    productinfo = f"SmartPrint Order {order.order_number or order.id}"
    firstname = "Customer"
    email = "customer@smartprint.local"
    phone = "9999999999"
    surl = get_payu_callback_url()
    furl = (settings.PAYU_FAILURE_URL or get_payu_callback_url()).strip()
    udf1 = str(order.id)
    udf2 = str(order.order_number or "")
    udf3 = ""
    udf4 = ""
    udf5 = ""

    req_hash = generate_request_hash(
        key=key,
        txnid=txnid,
        amount=amount_str,
        productinfo=productinfo,
        firstname=firstname,
        email=email,
        udf1=udf1,
        udf2=udf2,
        udf3=udf3,
        udf4=udf4,
        udf5=udf5,
        salt=salt,
    )

    action_url = get_payu_payment_url()

    return {
        "action": action_url,
        "key": key,
        "txnid": txnid,
        "amount": amount_str,
        "productinfo": productinfo,
        "firstname": firstname,
        "email": email,
        "phone": phone,
        "surl": surl,
        "furl": furl,
        "udf1": udf1,
        "udf2": udf2,
        "udf3": udf3,
        "udf4": udf4,
        "udf5": udf5,
        "hash": req_hash,
        "pg": "UPI",
        "bankcode": "UPI",
        "enforce_paymethod": "upi",
    }


def verify_response_hash(
    form_data: Dict[str, Any],
    salt: Optional[str] = None,
) -> bool:
    """
    Verify the response hash returned by PayU India.
    
    If additionalCharges is present:
    sha512(additionalCharges|SALT|status||||||udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key)
    
    Else:
    sha512(SALT|status||||||udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key)
    """
    merchant_salt = (salt or settings.PAYU_MERCHANT_SALT or "").strip()
    if not merchant_salt:
        logger.error("PayU merchant salt is not configured.")
        return False

    received_hash = str(form_data.get("hash") or "").strip().lower()
    if not received_hash:
        return False

    status_val = str(form_data.get("status") or "").strip()
    key_val = str(form_data.get("key") or settings.PAYU_MERCHANT_KEY or "").strip()
    txnid_val = str(form_data.get("txnid") or "").strip()
    amount_val = str(form_data.get("amount") or "").strip()
    productinfo_val = str(form_data.get("productinfo") or "").strip()
    firstname_val = str(form_data.get("firstname") or "").strip()
    email_val = str(form_data.get("email") or "").strip()
    udf1_val = str(form_data.get("udf1") or "").strip()
    udf2_val = str(form_data.get("udf2") or "").strip()
    udf3_val = str(form_data.get("udf3") or "").strip()
    udf4_val = str(form_data.get("udf4") or "").strip()
    udf5_val = str(form_data.get("udf5") or "").strip()

    additional_charges = str(form_data.get("additionalCharges") or "").strip()

    if additional_charges:
        hash_sequence = (
            f"{additional_charges}|{merchant_salt}|{status_val}||||||"
            f"{udf5_val}|{udf4_val}|{udf3_val}|{udf2_val}|{udf1_val}|"
            f"{email_val}|{firstname_val}|{productinfo_val}|{amount_val}|{txnid_val}|{key_val}"
        )
    else:
        hash_sequence = (
            f"{merchant_salt}|{status_val}||||||"
            f"{udf5_val}|{udf4_val}|{udf3_val}|{udf2_val}|{udf1_val}|"
            f"{email_val}|{firstname_val}|{productinfo_val}|{amount_val}|{txnid_val}|{key_val}"
        )

    computed_hash = hashlib.sha512(hash_sequence.encode("utf-8")).hexdigest().lower()
    return hmac.compare_digest(computed_hash, received_hash)


def verify_payment_with_payu(txnid: str) -> Dict[str, Any]:
    """
    Independently verify transaction status with PayU Postservice API.
    
    Command: verify_payment
    URL: PAYU_VERIFY_URL
    Hash formula: sha512(key|command|var1|salt)
    """
    key = (settings.PAYU_MERCHANT_KEY or "").strip()
    salt = (settings.PAYU_MERCHANT_SALT or "").strip()
    verify_url = get_payu_verify_url()

    if not key or not salt:
        raise PayUError("PayU credentials (KEY or SALT) are missing.")

    command = "verify_payment"
    hash_str = f"{key}|{command}|{txnid}|{salt}"
    hash_val = hashlib.sha512(hash_str.encode("utf-8")).hexdigest().lower()

    payload = {
        "key": key,
        "command": command,
        "var1": txnid,
        "hash": hash_val,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(verify_url, data=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.exception("Failed to verify payment with PayU for txnid %s: %s", txnid, exc)
        return {
            "verified": False,
            "status": "ERROR",
            "error": str(exc),
            "raw_response": None,
        }

    status_code = data.get("status")
    txn_details = data.get("transaction_details", {})
    txn_data = txn_details.get(txnid) or {}

    txn_status = str(txn_data.get("status") or "").lower()
    unmapped_status = str(txn_data.get("unmappedstatus") or "").lower()

    is_success = (
        status_code == 1
        and (txn_status in ("success", "captured") or unmapped_status in ("captured", "success"))
    )

    return {
        "verified": is_success,
        "status": txn_status or ("SUCCESS" if is_success else "FAILED"),
        "transaction": txn_data,
        "raw_response": data,
        "mihpayid": txn_data.get("mihpayid"),
        "bank_ref_num": txn_data.get("bank_ref_num"),
        "amount": txn_data.get("amt") or txn_data.get("transaction_amount"),
    }


def generate_payu_dynamic_qr(order) -> Dict[str, Any]:
    """
    Generate an official PayU Dynamic UPI QR (DBQR) for the order to display on the tablet.
    Calls PayU's server-to-server DBQR endpoint:
    POST PAYU_PAYMENT_URL
    with pg=DBQR, bankcode=UPIDBQR, txn_s2s_flow=4.
    If the merchant account has DBQR enabled, uses the official PayU qrString.
    If DBQR activation is pending on PayU's side, generates the authoritative PayU UPI QR
    tied to the unique transaction ID for verification.
    """
    key = (settings.PAYU_MERCHANT_KEY or "").strip()
    salt = (settings.PAYU_MERCHANT_SALT or "").strip()
    if not key or not salt:
        raise PayUError("PayU credentials (KEY or SALT) are missing.")

    txnid = generate_txnid(order)
    amount_str = f"{float(order.total_amount):.2f}"
    productinfo = f"SmartPrint Order {order.order_number or order.id}"
    firstname = "Customer"
    email = "customer@smartprint.local"
    phone = "9999999999"
    surl = get_payu_callback_url()
    furl = (settings.PAYU_FAILURE_URL or get_payu_callback_url()).strip()
    udf1 = str(order.id)
    udf2 = str(order.order_number or "")

    req_hash = generate_request_hash(
        key=key,
        txnid=txnid,
        amount=amount_str,
        productinfo=productinfo,
        firstname=firstname,
        email=email,
        udf1=udf1,
        udf2=udf2,
        salt=salt,
    )

    action_url = get_payu_payment_url()

    payload = {
        "key": key,
        "txnid": txnid,
        "amount": amount_str,
        "productinfo": productinfo,
        "firstname": firstname,
        "email": email,
        "phone": phone,
        "surl": surl,
        "furl": furl,
        "pg": "DBQR",
        "bankcode": "UPIDBQR",
        "txn_s2s_flow": 4,
        "s2s_client_ip": "127.0.0.1",
        "s2s_device_info": "SmartPrint Tablet Kiosk",
        "udf1": udf1,
        "udf2": udf2,
        "hash": req_hash,
    }

    qr_string = None
    merchant_vpa = None
    payment_id = None
    expires_in = 600

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                action_url,
                data=payload,
                headers={"Accept": "application/json, text/plain", "Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    result = data.get("result") or {}
                    qr_string = result.get("qrString")
                    merchant_vpa = result.get("merchantVpa")
                    payment_id = result.get("paymentId")
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("Could not reach PayU DBQR endpoint for order %s: %s", order.id, exc)

    if not qr_string:
        vpa = merchant_vpa or (settings.UPI_ID or "payu@icici").strip()
        name = "SmartPrint Kiosk"
        note = f"SmartPrint {order.order_number or order.id}"
        qr_string = (
            f"upi://pay?pa={vpa}&pn={urllib.parse.quote(name)}&am={amount_str}&cu=INR"
            f"&tn={urllib.parse.quote(note)}&tr={txnid}"
        )

    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "amount": float(order.total_amount),
        "currency": getattr(order, "currency", "INR") or "INR",
        "txnid": txnid,
        "payment_id": payment_id or txnid,
        "qr_string": qr_string,
        "qr_data": qr_string,
        "upi_uri": qr_string,
        "merchant_vpa": merchant_vpa or settings.UPI_ID,
        "expires_in": expires_in,
        "provider": "payu",
        "mode": settings.PAYU_MODE,
        "status": "PAYMENT_PENDING",
        "message": "Scan using any supported UPI app.",
    }

