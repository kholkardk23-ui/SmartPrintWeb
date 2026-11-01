import json
import logging
import urllib.parse
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Order, OrderStatus
from app.routes.orders import normalize_status
from app.schemas import (
    PaymentCheckoutResponse,
    PaymentStartResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
    PaymentStatusResponse,
)
from app.services import cashfree

logger = logging.getLogger("smartprint.payments")

router = APIRouter(prefix="/api/payments", tags=["Payments"])

PAID_STATUSES = (
    OrderStatus.PAID.value,
    OrderStatus.PRINTING.value,
    OrderStatus.COMPLETED.value,
)

PAYABLE_STATUSES = (
    OrderStatus.CREATED.value,
    OrderStatus.OPTIONS_SELECTED.value,
    OrderStatus.PAYMENT_PENDING.value,
)


def utc_now_naive() -> datetime:
    """Naive UTC timestamp, matching the timestamps stored in the database."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def find_order(db: Session, order_identifier: str) -> Order:
    """Find an order by its internal UUID or customer order number (e.g. SP-000001)."""
    return (
        db.query(Order)
        .filter(
            (Order.id == order_identifier)
            | (Order.order_number == order_identifier)
        )
        .first()
    )


def build_dynamic_upi_uri(order: Order) -> str:
    """
    Generate an authoritative dynamic UPI deep-link URI.

    NPCI Standard format:
    upi://pay?pa={vpa}&pn={name}&am={amount}&cu={currency}&tn={note}&tr={ref}
    """
    vpa = (settings.UPI_ID or "").strip() or "smartprint@upi"
    name = (settings.UPI_NAME or "").strip() or "SmartPrint Kiosk"
    params = {
        "pa": vpa,
        "pn": name,
        "am": f"{float(order.total_amount):.2f}",
        "cu": order.currency or "INR",
        "tn": f"SmartPrint {order.order_number or order.id}",
        "tr": order.order_number or order.id,
    }
    return f"upi://pay?{urllib.parse.urlencode(params)}"


def begin_payment(db: Session, order: Order) -> str:
    """Move an order into PAYMENT_PENDING and return its normalized status."""

    current = normalize_status(order.status)

    if current in PAID_STATUSES:
        return current

    if current not in PAYABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Payment cannot be started for order '{order.order_number or order.id}' "
                f"because its current status is '{current}'."
            ),
        )

    if current != OrderStatus.PAYMENT_PENDING.value:
        order.status = OrderStatus.PAYMENT_PENDING.value
        db.commit()
        db.refresh(order)

    return normalize_status(order.status)


def mark_paid(db: Session, order: Order, reference: str) -> str:
    """Record a successful payment and start printing. Safe to call twice."""

    current = normalize_status(order.status)

    if current in PAID_STATUSES:
        return current

    order.status = OrderStatus.PRINTING.value
    db.commit()
    db.refresh(order)

    logger.info(
        "Payment verified automatically for order '%s' (%s) | reference: %s",
        order.id,
        order.order_number,
        reference,
    )

    return normalize_status(order.status)


@router.post(
    "/{order_id}/start",
    response_model=PaymentStartResponse,
    summary="Start dynamic UPI payment for an order",
)
def start_payment(order_id: str, db: Session = Depends(get_db)):
    """
    Start the dynamic UPI payment process for an existing print order.

    Accepts orders in CREATED, OPTIONS_SELECTED, or PAYMENT_PENDING state.
    Generates a dynamic UPI URI and QR data containing the exact payable amount.
    """
    order = find_order(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found.",
        )

    # Payment must be explicitly enabled
    if not settings.PAYMENT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment system is currently disabled.",
        )

    # If already paid, return paid status immediately
    current_status = normalize_status(order.status)

    if current_status in PAID_STATUSES:
        upi_uri = build_dynamic_upi_uri(order)
        return PaymentStartResponse(
            order_id=order.id,
            order_number=order.order_number,
            amount=float(order.total_amount),
            currency=order.currency,
            payment_status="PAID",
            upi_id=(settings.UPI_ID or "").strip() or "smartprint@upi",
            upi_name=(settings.UPI_NAME or "").strip() or "SmartPrint Kiosk",
            upi_uri=upi_uri,
            qr_data=upi_uri,
        )

    current_status = begin_payment(db, order)

    upi_uri = build_dynamic_upi_uri(order)

    logger.info(
        "Dynamic UPI payment started for order '%s' (%s): %.2f %s | UPI: %s",
        order.id,
        order.order_number,
        order.total_amount,
        order.currency,
        upi_uri,
    )

    return PaymentStartResponse(
        order_id=order.id,
        order_number=order.order_number,
        amount=float(order.total_amount),
        currency=order.currency,
        payment_status="PAYMENT_PENDING",
        upi_id=(settings.UPI_ID or "").strip() or "smartprint@upi",
        upi_name=(settings.UPI_NAME or "").strip() or "SmartPrint Kiosk",
        upi_uri=upi_uri,
        qr_data=upi_uri,
    )


@router.post(
    "/{order_id}/verify",
    response_model=PaymentVerifyResponse,
    summary="Verify payment for an order",
)
def verify_payment(
    order_id: str,
    request: PaymentVerifyRequest = PaymentVerifyRequest(),
    db: Session = Depends(get_db),
):
    """
    Verify payment for an order.

    Accepts an optional reference/UTR number or automatically generates
    a verifiable demo reference.
    Transitions the order from PAYMENT_PENDING to PAID.
    """
    order = find_order(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found.",
        )

    # If already paid, return current status
    current_status = normalize_status(order.status)

    if current_status == OrderStatus.PAID.value:
        return PaymentVerifyResponse(
            order_id=order.id,
            order_number=order.order_number,
            amount=float(order.total_amount),
            currency=order.currency,
            payment_status="PAID",
            order_status=current_status,
            payment_reference="ALREADY_PAID",
        )

    valid_statuses = [
        OrderStatus.PAYMENT_PENDING.value,
        OrderStatus.CREATED.value,
        OrderStatus.OPTIONS_SELECTED.value,
    ]

    if current_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Payment verification requires an active order. "
                f"Current status is '{current_status}'."
            ),
        )

    ref = (request.payment_reference or "").strip()
    if not ref:
        ref = f"UPI-DEMO-{order.order_number or order.id[:8]}-{uuid.uuid4().hex[:6].upper()}"

    order.status = OrderStatus.PRINTING.value
    db.commit()
    db.refresh(order)

    logger.info(
        "Payment verified for order '%s' (%s) using reference '%s'",
        order.id,
        order.order_number,
        ref,
    )

    return PaymentVerifyResponse(
        order_id=order.id,
        order_number=order.order_number,
        amount=float(order.total_amount),
        currency=order.currency,
        payment_status="PAID",
        order_status=normalize_status(order.status),
        payment_reference=ref,
    )


@router.post(
    "/{order_id}/checkout",
    response_model=PaymentCheckoutResponse,
    summary="Create an automatic payment session for an order",
)
def create_checkout(order_id: str, db: Session = Depends(get_db)):
    """
    Prepare automatic payment collection for an order.

    With Cashfree credentials configured, a Cashfree order/payment session is
    returned and the frontend opens the Cashfree checkout. Without credentials
    the backend runs in demo mode and confirms the payment automatically.

    In both modes the frontend only polls the status endpoint - the customer
    never presses a "verify payment" button.
    """
    order = find_order(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found.",
        )

    if not settings.PAYMENT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment system is currently disabled.",
        )

    current_status = begin_payment(db, order)
    upi_uri = build_dynamic_upi_uri(order)
    provider = settings.effective_payment_provider

    common = {
        "order_id": order.id,
        "order_number": order.order_number,
        "amount": float(order.total_amount),
        "currency": order.currency,
        "upi_id": (settings.UPI_ID or "").strip() or "smartprint@upi",
        "upi_name": (settings.UPI_NAME or "").strip() or "SmartPrint Kiosk",
        "upi_uri": upi_uri,
        "qr_data": upi_uri,
        "status": current_status,
        "auto_verify_seconds": None,
    }

    if current_status in PAID_STATUSES:
        return PaymentCheckoutResponse(
            **common,
            provider=provider,
            mode=settings.CASHFREE_ENV if provider == "cashfree" else "demo",
            message="Payment already received.",
        )

    if provider == "cashfree":
        try:
            gateway_order = cashfree.create_order(order)
        except cashfree.CashfreeError as exc:
            logger.exception("Could not create Cashfree order for %s", order.id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not start the UPI payment: {exc}",
            )

        return PaymentCheckoutResponse(
            **common,
            provider="cashfree",
            mode=(settings.CASHFREE_ENV or "sandbox").strip().lower(),
            payment_session_id=gateway_order.get("payment_session_id"),
            checkout_url=(
                gateway_order.get("payment_link")
                or gateway_order.get("order_meta", {}).get("payment_link")
            ),
            message=(
                "Complete the payment in the Cashfree window. The order is "
                "created and printing starts automatically once the payment "
                "is confirmed."
            ),
        )

    return PaymentCheckoutResponse(
        **{
            **common,
            "auto_verify_seconds": settings.DEMO_AUTO_VERIFY_SECONDS,
        },
        provider="demo",
        mode="demo",
        message=(
            "Test mode: no real money is collected. The payment is confirmed "
            f"automatically after {settings.DEMO_AUTO_VERIFY_SECONDS} seconds."
        ),
    )


@router.post("/webhook/cashfree", include_in_schema=False)
async def cashfree_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Cashfree payment events and start printing immediately."""

    raw_body = await request.body()
    timestamp = request.headers.get("x-webhook-timestamp", "")
    signature = request.headers.get("x-webhook-signature", "")

    if not cashfree.verify_webhook_signature(raw_body, timestamp, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError:
        logger.warning("Ignoring Cashfree webhook with invalid JSON payload.")
        return {"status": "ignored"}

    data = payload.get("data") or {}
    order_info = data.get("order") or {}
    payment_info = data.get("payment") or {}

    gateway_id = str(order_info.get("order_id") or "")
    event_type = str(
        request.headers.get("x-webhook-type") or payload.get("type") or ""
    ).upper()
    payment_status = str(payment_info.get("payment_status") or "").upper()
    order_status = str(order_info.get("order_status") or "").upper()

    payment_succeeded = (
        "SUCCESS" in event_type
        or payment_status in ("SUCCESS", "PAID")
        or order_status in cashfree.PAID_GATEWAY_STATUSES
    )

    if not gateway_id or not payment_succeeded:
        return {"status": "ignored"}

    order = find_order(db, gateway_id)

    if order is None:
        # Gateway ids look like "SP-000001-20260101120000".
        order = find_order(db, gateway_id.rsplit("-", 1)[0])

    if order is None:
        logger.warning("Cashfree webhook references unknown order '%s'.", gateway_id)
        return {"status": "ignored"}

    mark_paid(
        db,
        order,
        str(payment_info.get("cf_payment_id") or f"CASHFREE-{gateway_id}"),
    )

    return {"status": "ok"}


@router.get(
    "/{order_id}/status",
    response_model=PaymentStatusResponse,
    summary="Get current payment status for an order",
)
def get_payment_status(order_id: str, db: Session = Depends(get_db)):
    """Check payment status for polling by the frontend."""
    order = find_order(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found.",
        )

    current_status = normalize_status(order.status)

    # Automatic verification: the customer never presses a button. While the
    # payment is pending we ask the gateway (or, in demo mode, wait for the
    # simulated confirmation) and move the order forward as soon as it is paid.
    if current_status == OrderStatus.PAYMENT_PENDING.value:
        if settings.effective_payment_provider == "cashfree":
            gateway_status = cashfree.fetch_payment_status(order)

            if gateway_status in cashfree.PAID_GATEWAY_STATUSES:
                current_status = mark_paid(
                    db,
                    order,
                    f"CASHFREE-{cashfree.gateway_order_id(order)}",
                )
        else:
            started_at = order.updated_at or order.created_at
            elapsed = (
                (utc_now_naive() - started_at).total_seconds()
                if started_at
                else 0
            )

            if elapsed >= settings.DEMO_AUTO_VERIFY_SECONDS:
                current_status = mark_paid(
                    db,
                    order,
                    f"DEMO-AUTO-{order.order_number or order.id}",
                )

    upi_uri = build_dynamic_upi_uri(order)
    is_paid = current_status in PAID_STATUSES

    return PaymentStatusResponse(
        order_id=order.id,
        order_number=order.order_number,
        amount=float(order.total_amount),
        currency=order.currency,
        status=current_status,
        payment_status="PAID" if is_paid else current_status,
        upi_id=(settings.UPI_ID or "").strip() or "smartprint@upi",
        upi_name=(settings.UPI_NAME or "").strip() or "SmartPrint Kiosk",
        upi_uri=upi_uri,
        is_paid=is_paid,
    )
