"""
PayU India Production Payment Gateway Integration Service
=========================================================
Provides PayU India UPI Smart Intent / Specific Intent Integration for SmartPrint.
Directly invokes native UPI applications:
- PhonePe (com.phonepe.app / phonepe://)
- Google Pay (com.google.android.apps.nbu.paisa.user / gpay://)
- Paytm (net.one97.paytm / paytm://)
- BHIM (in.org.npci.upiapp / upi://)
- Other UPI Apps (generic UPI app chooser)

Handles:
- Server-to-server intent initiation (pg=UPI, bankcode=INTENT, txn_s2s_flow=4, upiAppName)
- Outbound request hashing (SHA-512)
- Inbound response hash verification
- Independent server-to-server transaction verification (Postservice API)
- Unique transaction ID generation per attempt
- Device-specific intent URI formatting (Android intents, iOS URL schemes, desktop QR)
"""

import hashlib
import hmac
import logging
import uuid
from typing import Any, Dict, Optional

import httpx
from app.config import settings

logger = logging.getLogger("smartprint.payments.payu")

# Authoritative PayU India Production & Test endpoints
PAYU_PROD_PAYMENT_URL = "https://secure.payu.in/_payment"
PAYU_PROD_VERIFY_URL = "https://info.payu.in/merchant/postservice.php?form=2"

PAYU_TEST_PAYMENT_URL = "https://test.payu.in/_payment"
PAYU_TEST_VERIFY_URL = "https://test.payu.in/merchant/postservice.php?form=2"

# Supported UPI Applications specification
SUPPORTED_UPI_APPS = {
    "phonepe": {
        "name": "PhonePe",
        "app_name": "phonepe",
        "package_name": "com.phonepe.app",
        "ios_scheme": "phonepe://upi/pay?",
        "android_scheme": "phonepe://upi/pay?",
        "color": "#5f259f",
    },
    "googlepay": {
        "name": "Google Pay",
        "app_name": "googlepay",
        "package_name": "com.google.android.apps.nbu.paisa.user",
        "ios_scheme": "gpay://upi/pay?",
        "android_scheme": "gpay://upi/pay?",
        "color": "#1a73e8",
    },
    "paytm": {
        "name": "Paytm",
        "app_name": "paytm",
        "package_name": "net.one97.paytm",
        "ios_scheme": "paytm://upi/pay?",
        "android_scheme": "paytm://upi/pay?",
        "color": "#00b9f5",
    },
    "bhim": {
        "name": "BHIM",
        "app_name": "bhim",
        "package_name": "in.org.npci.upiapp",
        "ios_scheme": "upi://pay?",
        "android_scheme": "upi://pay?",
        "color": "#005a9c",
    },
    "genericintent": {
        "name": "Other UPI Apps",
        "app_name": "genericintent",
        "package_name": None,
        "ios_scheme": "upi://pay?",
        "android_scheme": "upi://pay?",
        "color": "#059669",
    },
}


class PayUError(Exception):
    """Raised when PayU processing fails or credentials are misconfigured."""
    pass


def is_production_mode() -> bool:
    """Return True if PayU is configured to run in production LIVE mode."""
    mode = (settings.PAYU_MODE or "test").strip().lower()
    return mode in ("live", "production")


def get_payu_payment_url() -> str:
    """Return the authoritative PayU S2S payment endpoint."""
    if is_production_mode():
        return PAYU_PROD_PAYMENT_URL
    if (settings.PAYU_PAYMENT_URL or "").strip():
        return settings.PAYU_PAYMENT_URL.strip()
    return PAYU_TEST_PAYMENT_URL


def get_payu_verify_url() -> str:
    """Return the authoritative PayU Postservice transaction verification endpoint."""
    if is_production_mode():
        return PAYU_PROD_VERIFY_URL
    if (settings.PAYU_VERIFY_URL or "").strip():
        return settings.PAYU_VERIFY_URL.strip()
    return PAYU_TEST_VERIFY_URL


def get_payu_callback_url() -> str:
    """Return the server callback URL (SURL/FURL) for PayU responses."""
    if (settings.PAYU_SUCCESS_URL or "").strip():
        return settings.PAYU_SUCCESS_URL.strip()
    backend_base = (getattr(settings, "BACKEND_URL", None) or "http://localhost:8000").rstrip("/")
    return f"{backend_base}/api/payments/payu/response"


def generate_txnid(order, force_new: bool = False) -> str:
    """
    Generate a unique transaction ID for PayU.
    PayU strictly requires a unique transaction ID for each payment attempt.
    """
    if not force_new:
        existing = getattr(order, "payment_session_id", None)
        if existing and str(existing).startswith("TXN-PAYU-"):
            return str(existing)

    order_ref = str(order.order_number or getattr(order, "id", "")[:8]).replace("-", "")
    unique_suffix = uuid.uuid4().hex[:8].upper()
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
    Generate SHA-512 request hash for PayU.
    Sequence:
    sha512(key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||SALT)
    """
    hash_sequence = (
        f"{key}|{txnid}|{amount}|{productinfo}|{firstname}|{email}|"
        f"{udf1}|{udf2}|{udf3}|{udf4}|{udf5}||||||{salt}"
    )
    return hashlib.sha512(hash_sequence.encode("utf-8")).hexdigest().lower()


def build_app_deep_links(intent_uri_data: str) -> Dict[str, Any]:
    """
    Construct platform-specific deep links (Android intent URLs and iOS URL schemes)
    from PayU's intentURIData string.
    """
    clean_query = intent_uri_data.lstrip("?").removeprefix("upi://pay?")
    universal_upi_uri = f"upi://pay?{clean_query}"
    android_generic_intent = f"intent://pay?{clean_query}#Intent;scheme=upi;end;"

    apps_result = {}
    for app_key, app_info in SUPPORTED_UPI_APPS.items():
        package = app_info["package_name"]
        if package:
            android_intent = f"intent://pay?{clean_query}#Intent;scheme=upi;package={package};end;"
        else:
            android_intent = android_generic_intent

        scheme_prefix = app_info["android_scheme"]
        clean_scheme = scheme_prefix if scheme_prefix.endswith("?") else f"{scheme_prefix}?"
        ios_prefix = app_info["ios_scheme"]
        clean_ios = ios_prefix if ios_prefix.endswith("?") else f"{ios_prefix}?"

        apps_result[app_key] = {
            "key": app_key,
            "name": app_info["name"],
            "app_name": app_info["app_name"],
            "package_name": package,
            "android_intent": android_intent,
            "android_scheme": f"{clean_scheme}{clean_query}",
            "ios_scheme": f"{clean_ios}{clean_query}",
            "universal_upi_uri": universal_upi_uri,
            "color": app_info["color"],
        }

    return {
        "intent_uri_data": clean_query,
        "universal_upi_uri": universal_upi_uri,
        "android_generic_intent": android_generic_intent,
        "apps": apps_result,
    }


def initiate_payu_smart_intent(
    order,
    upi_app: str = "genericintent",
    txnid: Optional[str] = None,
    client_ip: str = "127.0.0.1",
    device_info: str = "SmartPrint Web",
) -> Dict[str, Any]:
    """
    Initiate official PayU UPI Smart Intent / Specific Intent S2S transaction.
    Calls PayU's _payment endpoint with:
    - pg = "UPI"
    - bankcode = "INTENT"
    - txn_s2s_flow = 4
    - upiAppName = upi_app (e.g. phonepe, googlepay, paytm, bhim, genericintent)
    - s2s_client_ip, s2s_device_info
    Returns the intentURIData and deep links for direct app opening.
    """
    key = (settings.PAYU_MERCHANT_KEY or "").strip()
    salt = (settings.PAYU_MERCHANT_SALT or "").strip()
    if not key or not salt:
        raise PayUError("PayU credentials (PAYU_MERCHANT_KEY, PAYU_MERCHANT_SALT) are missing.")

    if is_production_mode() and (key in ("YOUR_PAYU_MERCHANT_KEY", "CHANGE_ME") or salt in ("YOUR_PAYU_MERCHANT_SALT", "CHANGE_ME")):
        raise PayUError("PayU Live mode is enabled, but production credentials are not configured in environment variables.")

    active_txnid = txnid or generate_txnid(order, force_new=True)
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
        txnid=active_txnid,
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

    payload = {
        "key": key,
        "txnid": active_txnid,
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
        "bankcode": "INTENT",
        "txn_s2s_flow": 4,
        "upiAppName": upi_app,
        "s2s_client_ip": client_ip,
        "s2s_device_info": device_info,
    }

    intent_uri_data = None
    merchant_vpa = None
    merchant_name = None
    payment_id = None
    error_detail = None
    raw_response = None

    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.post(
                action_url,
                data=payload,
                headers={"Accept": "application/json, text/plain", "Content-Type": "application/x-www-form-urlencoded"},
            )
            try:
                raw_response = resp.json()
            except Exception:
                raw_response = {"text": resp.text}

            if resp.status_code == 200 and isinstance(raw_response, dict):
                result = raw_response.get("result") or {}
                intent_uri_data = result.get("intentURIData")
                merchant_vpa = result.get("merchantVpa")
                merchant_name = result.get("merchantName")
                payment_id = result.get("paymentId")

                if not intent_uri_data:
                    meta = raw_response.get("metaData") or {}
                    error_detail = meta.get("message") or raw_response.get("message") or raw_response.get("error")
            else:
                error_detail = f"PayU responded with HTTP {resp.status_code}: {resp.text[:300]}"
    except Exception as exc:
        logger.exception("Failed to connect to PayU S2S Intent endpoint for order %s: %s", order.id, exc)
        error_detail = str(exc)

    backend_base = (getattr(settings, "BACKEND_URL", None) or "http://localhost:8000").rstrip("/")
    fallback_checkout_url = f"{backend_base}/api/payments/{order.id}/payu-checkout"

    if intent_uri_data:
        deep_links = build_app_deep_links(intent_uri_data)
        return {
            "success": True,
            "order_id": order.id,
            "order_number": order.order_number,
            "amount": float(order.total_amount),
            "currency": getattr(order, "currency", "INR") or "INR",
            "txnid": active_txnid,
            "payment_id": payment_id or active_txnid,
            "merchant_vpa": merchant_vpa or settings.UPI_ID,
            "merchant_name": merchant_name or "SmartPrint",
            "intent_uri_data": deep_links["intent_uri_data"],
            "universal_upi_uri": deep_links["universal_upi_uri"],
            "android_generic_intent": deep_links["android_generic_intent"],
            "apps": deep_links["apps"],
            "selected_app": upi_app,
            "checkout_url": fallback_checkout_url,
            "qr_data": deep_links["universal_upi_uri"],
            "qr_type": "payu_smart_intent",
            "activation_required": False,
            "activation_details": None,
            "message": "PayU UPI Smart Intent ready. Select your preferred UPI application.",
            "raw_response": raw_response,
        }
    else:
        logger.warning(
            "PayU Smart Intent not returned for order %s (app=%s): %s",
            order.order_number or order.id, upi_app, error_detail
        )
        return {
            "success": False,
            "order_id": order.id,
            "order_number": order.order_number,
            "amount": float(order.total_amount),
            "currency": getattr(order, "currency", "INR") or "INR",
            "txnid": active_txnid,
            "payment_id": active_txnid,
            "intent_uri_data": None,
            "universal_upi_uri": None,
            "android_generic_intent": None,
            "apps": {},
            "selected_app": upi_app,
            "checkout_url": fallback_checkout_url,
            "qr_data": fallback_checkout_url,
            "qr_type": "payu_smart_intent_pending_activation",
            "activation_required": True,
            "activation_details": (
                "PayU UPI Smart Intent / S2S Intent API is pending merchant activation on this PayU merchant key. "
                "To activate: Contact your PayU Key Account Manager (KAM) or email care@payu.in to enable 'UPI Smart Intent / S2S Intent API' "
                f"for merchant key '{key}'. (Error from gateway: {error_detail or 'Intent not returned'})"
            ),
            "message": f"PayU UPI Smart Intent requires merchant account activation: {error_detail or 'Activation pending'}",
            "raw_response": raw_response,
        }


def prepare_payment_payload(order, txnid: Optional[str] = None) -> Dict[str, Any]:
    """
    Prepare standard parameters for PayU form submission (fallback).
    """
    key = (settings.PAYU_MERCHANT_KEY or "").strip()
    salt = (settings.PAYU_MERCHANT_SALT or "").strip()
    if not key or not salt:
        raise PayUError("PayU credentials (PAYU_MERCHANT_KEY, PAYU_MERCHANT_SALT) are missing.")

    if is_production_mode() and (key in ("YOUR_PAYU_MERCHANT_KEY", "CHANGE_ME") or salt in ("YOUR_PAYU_MERCHANT_SALT", "CHANGE_ME")):
        raise PayUError("PayU Live mode is enabled, but production credentials are not configured in environment variables.")

    active_txnid = txnid or generate_txnid(order, force_new=True)
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
        txnid=active_txnid,
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
        "txnid": active_txnid,
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
        "default_paymethod": "upi",
        "enforce_paymethod": "upi",
        "drop_category": "CC|DC|NB|EMI|CASH|BNPL|REWARD",
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
    if not txn_data and isinstance(txn_details, dict):
        clean_target = str(txnid).strip().lower()
        for k, v in txn_details.items():
            if str(k).strip().lower() == clean_target:
                txn_data = v
                break

    txn_status = str(txn_data.get("status") or "").lower()
    unmapped_status = str(txn_data.get("unmappedstatus") or "").lower()

    is_success = (
        str(status_code) in ("1", "success")
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
        "mode": txn_data.get("mode") or "UPI",
    }


def generate_payu_dynamic_qr(order) -> Dict[str, Any]:
    """
    PayU Smart Intent QR for tablet or desktop display.
    Uses PayU S2S Intent URI. DBQR / UPIDBQR is NOT used.
    """
    try:
        intent_res = initiate_payu_smart_intent(order, upi_app="genericintent")
        if intent_res.get("success") and intent_res.get("universal_upi_uri"):
            active_qr = intent_res["universal_upi_uri"]
            return {
                "order_id": order.id,
                "order_number": order.order_number,
                "amount": float(order.total_amount),
                "currency": getattr(order, "currency", "INR") or "INR",
                "txnid": intent_res.get("txnid"),
                "payment_id": intent_res.get("payment_id"),
                "qr_string": active_qr,
                "qr_data": active_qr,
                "upi_uri": active_qr,
                "universal_upi_uri": active_qr,
                "checkout_url": intent_res.get("checkout_url"),
                "qr_type": "payu_smart_intent",
                "dbqr_active": False,
                "instructions": "Scan using Google Pay, PhonePe, Paytm, BHIM, or any UPI app.",
                "activation_required": False,
                "activation_details": None,
                "merchant_vpa": intent_res.get("merchant_vpa"),
                "expires_in": 600,
                "provider": "payu",
                "mode": settings.PAYU_MODE,
                "status": "PAYMENT_PENDING",
                "message": "PayU Smart Intent QR active.",
            }
    except Exception as exc:
        logger.warning("Could not initiate Smart Intent QR for order %s: %s", order.id, exc)

    backend_base = (getattr(settings, "BACKEND_URL", None) or "http://localhost:8000").rstrip("/")
    checkout_url = (intent_res.get("checkout_url") if "intent_res" in locals() else None) or f"{backend_base}/api/payments/{order.id}/payu-checkout"
    txnid = (intent_res.get("txnid") if "intent_res" in locals() else None) or generate_txnid(order, force_new=False)
    activation_req = intent_res.get("activation_required", True) if "intent_res" in locals() else False
    activation_det = intent_res.get("activation_details") if "intent_res" in locals() else None

    # Exclusively use official PayU endpoints. Do not construct arbitrary manual UPI URIs.
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "amount": float(order.total_amount),
        "currency": getattr(order, "currency", "INR") or "INR",
        "txnid": txnid,
        "payment_id": None,
        "qr_string": checkout_url,
        "qr_data": checkout_url,
        "upi_uri": None,
        "universal_upi_uri": None,
        "checkout_url": checkout_url,
        "qr_type": "payu_hosted_checkout",
        "dbqr_active": False,
        "instructions": "Complete payment via PayU Hosted Checkout using UPI, Cards or Net Banking.",
        "activation_required": activation_req,
        "activation_details": activation_det,
        "merchant_vpa": intent_res.get("merchant_vpa") if "intent_res" in locals() else None,
        "expires_in": 600,
        "provider": "payu",
        "mode": settings.PAYU_MODE,
        "status": "PAYMENT_PENDING",
        "message": intent_res.get("message", "PayU payment session active.") if "intent_res" in locals() else "PayU payment session active.",
    }
