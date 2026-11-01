import base64
import hashlib
import hmac
import json
import logging
import re
from datetime import datetime

import httpx

from app.config import settings

logger = logging.getLogger("smartprint.cashfree")

# Order statuses returned by Cashfree that mean "money received".
PAID_GATEWAY_STATUSES = {"PAID"}


class CashfreeError(Exception):
    """Raised when the Cashfree API cannot complete a request."""


def _headers() -> dict:
    return {
        "x-client-id": settings.CASHFREE_CLIENT_ID.strip(),
        "x-client-secret": settings.CASHFREE_CLIENT_SECRET.strip(),
        "x-api-version": settings.CASHFREE_API_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def gateway_order_id(order) -> str:
    """
    Build a deterministic Cashfree order id for a SmartPrint order.

    Cashfree requires unique, URL-safe ids of at most 50 characters. Deriving
    the id from the order number and creation time makes retries idempotent
    without needing an extra database table.
    """

    created = order.created_at or datetime.utcnow()

    if isinstance(created, str):
        created_part = re.sub(r"[^0-9]", "", created)[:14]
    else:
        created_part = created.strftime("%Y%m%d%H%M%S")

    raw = f"{order.order_number or order.id}-{created_part}"
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", raw)

    return safe[:50]


def _request(method: str, path: str, **kwargs) -> dict:
    if not settings.cashfree_configured:
        raise CashfreeError(
            "Cashfree credentials are missing. Set CASHFREE_CLIENT_ID and "
            "CASHFREE_CLIENT_SECRET, or use PAYMENT_PROVIDER=demo."
        )

    url = f"{settings.cashfree_base_url}{path}"

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.request(method, url, headers=_headers(), **kwargs)
    except httpx.HTTPError as exc:
        logger.warning("Cashfree request failed: %s %s (%s)", method, path, exc)
        raise CashfreeError(f"Could not reach the payment gateway: {exc}") from exc

    if response.status_code >= 400:
        logger.warning(
            "Cashfree error %s for %s %s: %s",
            response.status_code,
            method,
            path,
            response.text[:500],
        )
        raise CashfreeError(
            f"Payment gateway rejected the request ({response.status_code})."
        )

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise CashfreeError("Payment gateway returned an invalid response.") from exc


def create_order(order) -> dict:
    """Create (or reuse) a Cashfree order and return its payment session."""

    order_id = gateway_order_id(order)

    payload = {
        "order_id": order_id,
        "order_amount": float(order.total_amount),
        "order_currency": order.currency or "INR",
        "customer_details": {
            "customer_id": (order.order_number or order.id)[:50],
            "customer_phone": settings.CASHFREE_CUSTOMER_PHONE,
            "customer_email": settings.CASHFREE_CUSTOMER_EMAIL,
        },
        "order_meta": {
            "return_url": (
                f"{settings.CASHFREE_RETURN_URL.rstrip('/')}"
                f"/?order_id={order.order_number or order.id}"
            ),
        },
        "order_note": f"SmartPrint {order.order_number or order.id}",
    }

    try:
        return _request("POST", "/orders", json=payload)
    except CashfreeError as exc:
        # A retry for the same print order reuses the same Cashfree order id.
        # If it already exists, fall through and fetch its current state.
        if "409" not in str(exc) and "already" not in str(exc).lower():
            raise

    return fetch_order(order_id)


def fetch_order(order_id: str) -> dict:
    """Fetch the authoritative state of a Cashfree order."""

    return _request("GET", f"/orders/{order_id}")


def fetch_payment_status(order) -> str:
    """Return the gateway order status, or 'UNKNOWN' if it cannot be read."""

    try:
        data = fetch_order(gateway_order_id(order))
    except CashfreeError as exc:
        logger.warning("Cashfree status lookup failed: %s", exc)
        return "UNKNOWN"

    return str(data.get("order_status") or "UNKNOWN").upper()


def verify_webhook_signature(
    raw_body: bytes,
    timestamp: str,
    signature: str,
) -> bool:
    """Validate the x-webhook-signature header sent by Cashfree."""

    secret = (settings.CASHFREE_WEBHOOK_SECRET or "").strip()

    if not secret:
        # No secret configured (local/demo): accept the payload.
        return True

    if not timestamp or not signature:
        return False

    signed_payload = timestamp.encode("utf-8") + raw_body
    expected = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    return hmac.compare_digest(expected, signature)
