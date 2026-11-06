import hashlib
import hmac
import logging
from typing import Optional, Dict

import razorpay
from app.config import settings

logger = logging.getLogger("smartprint.razorpay")

_razorpay_client: Optional[razorpay.Client] = None
_order_cache: Dict[str, dict] = {}


def get_client() -> razorpay.Client:
    """Return an initialized Razorpay Client instance."""
    global _razorpay_client
    if not settings.razorpay_configured:
        raise ValueError(
            "Razorpay credentials are missing. Set RAZORPAY_KEY_ID and "
            "RAZORPAY_KEY_SECRET in backend/.env."
        )
    if _razorpay_client is None:
        _razorpay_client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID.strip(), settings.RAZORPAY_KEY_SECRET.strip())
        )
    return _razorpay_client


def create_order(order) -> dict:
    """
    Create or reuse a Razorpay order for a SmartPrint order.
    Prevents duplicate Razorpay orders for the same SmartPrint order.
    """
    order_key = str(order.order_number or order.id)
    expected_amount = int(round(float(order.total_amount) * 100))

    if order_key in _order_cache:
        cached = _order_cache[order_key]
        if cached.get("amount") == expected_amount:
            return cached

    client = get_client()
    amount_paise = max(expected_amount, 100)

    receipt = str(order.order_number or order.id)[:40]

    data = {
        "amount": amount_paise,
        "currency": order.currency or "INR",
        "receipt": receipt,
        "notes": {
            "order_id": str(order.id),
            "order_number": str(order.order_number or ""),
        },
        "payment_capture": 1,
    }

    logger.info("Creating Razorpay order for %s, amount: %d paise", receipt, amount_paise)
    rzp_order = client.order.create(data=data)
    _order_cache[order_key] = rzp_order
    return rzp_order


def verify_payment_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """
    Verify payment signature returned by Razorpay Checkout.
    HMAC-SHA256 of (razorpay_order_id + '|' + razorpay_payment_id) with key_secret.
    """
    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        return False

    secret = (settings.RAZORPAY_KEY_SECRET or "").strip()
    if not secret:
        return False

    msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        msg,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, razorpay_signature)


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """
    Verify X-Razorpay-Signature header against the raw webhook body.
    """
    secret = (settings.RAZORPAY_WEBHOOK_SECRET or "").strip()
    if not secret:
        secret = (settings.RAZORPAY_KEY_SECRET or "").strip()

    if not signature or not secret:
        return False

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)


def fetch_payment(payment_id: str) -> Optional[dict]:
    """Fetch payment status from Razorpay API."""
    try:
        client = get_client()
        return client.payment.fetch(payment_id)
    except Exception as exc:
        logger.warning("Failed to fetch Razorpay payment %s: %s", payment_id, exc)
        return None


def fetch_order_payments(razorpay_order_id: str) -> list:
    """Fetch payments associated with a Razorpay order."""
    try:
        client = get_client()
        res = client.order.payments(razorpay_order_id)
        return res.get("items", []) if isinstance(res, dict) else res
    except Exception as exc:
        logger.warning("Failed to fetch payments for Razorpay order %s: %s", razorpay_order_id, exc)
        return []

