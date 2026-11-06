from typing import Optional, Dict, Any
import json
import logging
import urllib.parse
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Order, OrderStatus, PaymentTransaction
from app.routes.orders import normalize_status
from app.schemas import (
    PaymentCheckoutResponse,
    PaymentStartResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
    PaymentStatusResponse,
    RazorpayVerifyRequest,
)
from app.services import cashfree, payu_service, razorpay_service, youpi_service

logger = logging.getLogger("smartprint.payments")

router = APIRouter(prefix="/api/payments", tags=["Payments"])

PAID_STATUSES = (
    OrderStatus.CONFIRMED.value,
    OrderStatus.PAID.value,
    OrderStatus.QUEUED.value,
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


def find_order(db: Session, order_identifier: str) -> Optional[Order]:
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
    vpa = (settings.UPI_ID or "").strip()
    if not vpa:
        return ""
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


def record_payment_transaction(
    db: Session,
    order: Order,
    txnid: str,
    amount: float,
    payment_gateway: str = "PAYU",
    payment_status: str = "INITIATED",
    payment_mode: Optional[str] = None,
    mihpayid: Optional[str] = None,
    gateway_response: Optional[Any] = None,
) -> PaymentTransaction:
    """Record or update a payment transaction attempt in payment_transactions table."""
    txn = db.query(PaymentTransaction).filter(PaymentTransaction.txnid == txnid).first()
    raw_json = json.dumps(gateway_response) if gateway_response else None
    if not txn:
        txn = PaymentTransaction(
            id=str(uuid.uuid4()),
            order_id=order.id,
            txnid=txnid,
            mihpayid=mihpayid,
            amount=amount,
            payment_gateway=payment_gateway,
            payment_mode=payment_mode,
            payment_status=payment_status,
            gateway_response=raw_json,
        )
        db.add(txn)
    else:
        if mihpayid:
            txn.mihpayid = mihpayid
        if payment_mode:
            txn.payment_mode = payment_mode
        if payment_status:
            txn.payment_status = payment_status
        if raw_json:
            txn.gateway_response = raw_json
    db.commit()
    db.refresh(txn)
    return txn


def mark_paid(
    db: Session,
    order: Order,
    reference: str,
    payment_time: Optional[datetime] = None,
    payment_session_id: Optional[str] = None,
) -> str:
    """Record a successful payment and confirm the order. Safe and idempotent."""
    current = normalize_status(order.status)
    now = payment_time or utc_now_naive()

    order.payment_status = "SUCCESS"
    if hasattr(order, "is_paid"):
        order.is_paid = True

    if reference and not getattr(order, "payment_reference", None):
        order.payment_reference = reference
    elif not getattr(order, "payment_reference", None):
        order.payment_reference = f"RZP-{order.order_number or order.id[:8]}-{uuid.uuid4().hex[:6].upper()}"

    if payment_session_id and not getattr(order, "payment_session_id", None):
        order.payment_session_id = payment_session_id

    if not getattr(order, "payment_timestamp", None):
        order.payment_timestamp = now

    if current not in PAID_STATUSES:
        order.status = OrderStatus.CONFIRMED.value

    # Update matching PaymentTransaction if exists
    if payment_session_id:
        try:
            txn = db.query(PaymentTransaction).filter(PaymentTransaction.txnid == str(payment_session_id)).first()
            if txn:
                txn.payment_status = "SUCCESS"
                if reference:
                    txn.mihpayid = reference
        except Exception as e:
            logger.debug("Could not update PaymentTransaction in mark_paid: %s", e)

    db.commit()
    db.refresh(order)

    logger.info(
        "Payment verified for order '%s' (%s) | reference: %s | session: %s | status: %s",
        order.id,
        order.order_number,
        order.payment_reference,
        getattr(order, "payment_session_id", None),
        order.status,
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

    if not settings.PAYMENT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment system is currently disabled.",
        )

    current_status = normalize_status(order.status)

    if current_status in PAID_STATUSES:
        upi_uri = build_dynamic_upi_uri(order)
        return PaymentStartResponse(
            order_id=order.id,
            order_number=order.order_number,
            amount=float(order.total_amount),
            currency=order.currency,
            payment_status="PAID",
            upi_id=(settings.UPI_ID or "").strip(),
            upi_name=(settings.UPI_NAME or "").strip() or "SmartPrint Kiosk",
            upi_uri=upi_uri,
            qr_data=upi_uri,
        )

    current_status = begin_payment(db, order)
    upi_uri = build_dynamic_upi_uri(order)

    logger.info(
        "Payment started for order '%s' (%s): %.2f %s | UPI: %s",
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
        upi_id=(settings.UPI_ID or "").strip(),
        upi_name=(settings.UPI_NAME or "").strip() or "SmartPrint Kiosk",
        upi_uri=upi_uri,
        qr_data=upi_uri,
    )


@router.post(
    "/{order_id}/checkout",
    response_model=PaymentCheckoutResponse,
    summary="Create an automatic payment session for an order",
)
def create_checkout(
    order_id: str,
    provider: Optional[str] = None,
    upi_app: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Prepare payment checkout session for an order.
    Supports PayU Smart Intent (PhonePe, Google Pay, Paytm, BHIM, generic),
    YouPI-PG, Razorpay, Cashfree, or demo mode.
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

    req_provider = (provider or "").strip().lower()
    if req_provider in ("payu", "youpi", "razorpay", "cashfree", "demo"):
        chosen_provider = req_provider
    else:
        chosen_provider = settings.effective_payment_provider

    common = {
        "order_id": order.id,
        "order_number": order.order_number,
        "amount": float(order.total_amount),
        "currency": order.currency,
        "upi_id": (settings.UPI_ID or "").strip(),
        "upi_name": (settings.UPI_NAME or "").strip() or "SmartPrint Kiosk",
        "upi_uri": upi_uri,
        "qr_data": upi_uri,
        "status": current_status,
        "auto_verify_seconds": None,
    }

    if current_status in PAID_STATUSES:
        return PaymentCheckoutResponse(
            **common,
            provider=chosen_provider,
            mode=settings.PAYU_MODE if chosen_provider == "payu" else ("test" if chosen_provider in ("razorpay", "youpi") else (settings.CASHFREE_ENV if chosen_provider == "cashfree" else "demo")),
            message="Payment already received.",
        )

    if chosen_provider == "payu":
        if not settings.payu_configured:
            logger.warning(
                "PayU checkout requested for order '%s', but PayU credentials are not configured.",
                order.order_number or order.id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="PayU payment gateway is not configured. Please set PAYU_MERCHANT_KEY and PAYU_MERCHANT_SALT in environment variables.",
            )
        try:
            txnid = payu_service.generate_txnid(order, force_new=True)
            order.payment_session_id = txnid
            db.commit()
            db.refresh(order)

            # Record initiated payment transaction attempt
            record_payment_transaction(
                db=db,
                order=order,
                txnid=txnid,
                amount=float(order.total_amount),
                payment_gateway="PAYU",
                payment_status="INITIATED",
                payment_mode=upi_app or "UPI_INTENT",
            )

            client_ip = (
                request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                if request and request.headers.get("x-forwarded-for")
                else (request.client.host if request and request.client else "127.0.0.1")
            )
            device_info = (
                request.headers.get("user-agent", "SmartPrint Web Mobile")
                if request
                else "SmartPrint Web Mobile"
            )

            # Initiate PayU S2S Smart Intent (with specific or generic app code)
            target_app = (upi_app or "genericintent").strip().lower()
            intent_res = payu_service.initiate_payu_smart_intent(
                order=order,
                upi_app=target_app,
                txnid=txnid,
                client_ip=client_ip,
                device_info=device_info,
            )

            payu_data = payu_service.prepare_payment_payload(order, txnid=txnid)
        except payu_service.PayUError as exc:
            logger.warning("PayU configuration error for order %s: %s", order.id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"PayU payment gateway configuration error: {exc}",
            )
        except Exception as exc:
            logger.exception("Could not initialize PayU Smart Intent for %s: %s", order.id, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not initialize PayU payment: {exc}",
            )

        active_upi_uri = intent_res.get("universal_upi_uri") or upi_uri
        payu_common = {k: v for k, v in common.items() if k not in ("upi_uri", "qr_data")}
        return PaymentCheckoutResponse(
            **payu_common,
            provider="payu",
            mode=settings.PAYU_MODE,
            checkout_url=payu_data.get("action") or intent_res.get("checkout_url"),
            payment_session_id=txnid,
            payu_params=payu_data,
            qr_type=intent_res.get("qr_type", "payu_smart_intent"),
            dbqr_active=False,
            instructions="Select your preferred UPI app (PhonePe, Google Pay, Paytm, BHIM) to complete payment.",
            activation_required=intent_res.get("activation_required", False),
            activation_details=intent_res.get("activation_details"),
            upi_intent=intent_res if intent_res.get("success") else None,
            upi_apps=intent_res.get("apps") if intent_res.get("success") else None,
            intent_uri_data=intent_res.get("intent_uri_data"),
            selected_app=target_app,
            upi_uri=active_upi_uri,
            qr_data=active_upi_uri,
            message=intent_res.get("message", "PayU UPI Smart Intent ready."),
        )

    if chosen_provider == "youpi":
        session_id = getattr(order, "payment_session_id", None)
        checkout_url = None
        try:
            youpi_data = youpi_service.create_payment_session(order)
            session_id = youpi_data.get("paymentId") or session_id
            checkout_url = youpi_data.get("checkoutUrl")
            if youpi_data.get("upiUri"):
                upi_uri = youpi_data.get("upiUri")

            if session_id and not getattr(order, "payment_session_id", None):
                order.payment_session_id = session_id
                db.commit()
                db.refresh(order)
        except Exception as exc:
            logger.exception("Could not initialize YouPI payment for %s: %s", order.id, exc)
            if not session_id:
                session_id = f"YOUPI-LOCAL-{order.order_number or order.id}"

        return PaymentCheckoutResponse(
            **{
                **common,
                "upi_uri": upi_uri,
                "qr_data": upi_uri,
            },
            provider="youpi",
            mode="mock",
            payment_session_id=session_id,
            checkout_url=checkout_url,
            message="Scan the dynamic UPI QR code with any UPI app (GPay, PhonePe, Paytm, BHIM).",
        )

    if chosen_provider == "razorpay":
        try:
            rzp_order = razorpay_service.create_order(order)
        except Exception as exc:
            logger.exception("Could not create Razorpay order for %s", order.id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not initialize Razorpay payment: {exc}",
            )

        return PaymentCheckoutResponse(
            **common,
            provider="razorpay",
            mode="test" if "test" in (settings.RAZORPAY_KEY_ID or "").lower() else "live",
            razorpay_order_id=rzp_order["id"],
            razorpay_key_id=settings.RAZORPAY_KEY_ID.strip(),
            message="Complete payment using Razorpay Checkout (UPI, Cards, NetBanking, QR).",
        )

    if chosen_provider == "cashfree":
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
            message="Complete payment in Cashfree window.",
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


@router.post(
    "/{order_id}/qr",
    response_model=PaymentCheckoutResponse,
    summary="Generate PayU Dynamic UPI QR for tablet payment display",
)
def get_order_qr(order_id: str, db: Session = Depends(get_db)):
    """
    Generate or retrieve the PayU-supported dynamic payment QR for an order.
    Used by the SmartPrint payment tablet kiosk.
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
    if current_status in PAID_STATUSES:
        return PaymentCheckoutResponse(
            order_id=order.id,
            order_number=order.order_number,
            amount=float(order.total_amount),
            currency=order.currency,
            provider="payu",
            mode=settings.PAYU_MODE,
            status=current_status,
            upi_id=(settings.UPI_ID or "").strip(),
            upi_name=(settings.UPI_NAME or "SmartPrint Kiosk").strip(),
            message="Payment already received.",
        )

    if not settings.payu_configured:
        logger.warning(
            "PayU QR requested for order '%s', but PayU credentials are not configured.",
            order.order_number or order.id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PayU payment gateway is not configured. Please set PAYU_MERCHANT_KEY and PAYU_MERCHANT_SALT in environment variables.",
        )
    try:
        qr_info = payu_service.generate_payu_dynamic_qr(order)
        txnid = qr_info.get("txnid")
        if txnid and getattr(order, "payment_session_id", None) != txnid:
            order.payment_session_id = txnid
            db.commit()
            db.refresh(order)
        if txnid:
            record_payment_transaction(
                db=db,
                order=order,
                txnid=txnid,
                amount=float(order.total_amount),
                payment_gateway="PAYU",
                payment_status="INITIATED",
                payment_mode="UPI_QR",
            )
    except payu_service.PayUError as exc:
        logger.warning("PayU error generating QR for %s: %s", order.id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PayU payment gateway configuration error: {exc}",
        )
    except Exception as exc:
        logger.exception("Could not generate PayU dynamic QR for %s: %s", order.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not generate PayU payment QR: {exc}",
        )

    active_upi_uri = (
        qr_info.get("universal_upi_uri")
        or qr_info.get("upi_uri")
        or (qr_info.get("qr_data") if str(qr_info.get("qr_data") or "").startswith("upi://") else None)
    )
    active_qr_data = active_upi_uri or qr_info.get("qr_data") or qr_info.get("checkout_url")
    active_qr_type = qr_info.get("qr_type") or ("payu_smart_intent" if active_upi_uri else "payu_hosted_checkout")
    default_instructions = (
        "Scan the QR code using Google Pay, PhonePe, Paytm, BHIM, or any UPI app to complete payment."
        if active_upi_uri
        else "Complete payment via PayU Hosted Checkout using UPI, Cards or Net Banking."
    )

    return PaymentCheckoutResponse(
        order_id=order.id,
        order_number=order.order_number,
        amount=float(order.total_amount),
        currency=order.currency,
        provider="payu",
        mode=settings.PAYU_MODE,
        payment_session_id=qr_info.get("txnid") or getattr(order, "payment_session_id", None),
        checkout_url=qr_info.get("checkout_url") or payu_service.get_payu_payment_url(),
        upi_id=(settings.UPI_ID or "").strip(),
        upi_name=(settings.UPI_NAME or "SmartPrint Kiosk").strip(),
        upi_uri=active_upi_uri,
        qr_data=active_qr_data,
        qr_type=active_qr_type,
        dbqr_active=False,
        instructions=qr_info.get("instructions") or default_instructions,
        activation_required=qr_info.get("activation_required", False),
        activation_details=qr_info.get("activation_details"),
        status=current_status,
        message=qr_info.get("message", "PayU dynamic UPI QR active."),
    )


@router.post(
    "/{order_id}/payu-intent",
    summary="Get PayU Smart Intent deep links for a specific UPI application",
)
def get_payu_app_intent(
    order_id: str,
    app: Optional[str] = "genericintent",
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Fetch PayU S2S Smart Intent links for a selected UPI app:
    phonepe, googlepay, paytm, bhim, or genericintent.
    """
    order = find_order(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if not settings.payu_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PayU payment gateway is not configured.",
        )

    begin_payment(db, order)
    txnid = payu_service.generate_txnid(order, force_new=True)
    order.payment_session_id = txnid
    db.commit()
    db.refresh(order)

    record_payment_transaction(
        db=db,
        order=order,
        txnid=txnid,
        amount=float(order.total_amount),
        payment_gateway="PAYU",
        payment_status="INITIATED",
        payment_mode=app or "UPI_INTENT",
    )

    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if request and request.headers.get("x-forwarded-for")
        else (request.client.host if request and request.client else "127.0.0.1")
    )
    device_info = (
        request.headers.get("user-agent", "SmartPrint Web Mobile")
        if request
        else "SmartPrint Web Mobile"
    )

    intent_res = payu_service.initiate_payu_smart_intent(
        order=order,
        upi_app=app or "genericintent",
        txnid=txnid,
        client_ip=client_ip,
        device_info=device_info,
    )

    return intent_res


@router.post(
    "/{order_id}/verify-razorpay",
    response_model=PaymentVerifyResponse,
    summary="Verify Razorpay Checkout payment signature",
)
def verify_razorpay_payment(
    order_id: str,
    payload: RazorpayVerifyRequest,
    db: Session = Depends(get_db),
):
    """
    Verify payment signature returned by Razorpay Checkout.
    Automatically confirms order ONLY after signature is verified.
    """
    order = find_order(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found.",
        )

    current_status = normalize_status(order.status)
    if current_status in PAID_STATUSES or getattr(order, "payment_status", None) in ("PAID", "SUCCESS"):
        return PaymentVerifyResponse(
            order_id=order.id,
            order_number=order.order_number,
            amount=float(order.total_amount),
            currency=order.currency,
            payment_status="PAID",
            order_status=current_status,
            payment_reference=getattr(order, "payment_reference", None) or payload.razorpay_payment_id,
            payment_timestamp=getattr(order, "payment_timestamp", None),
        )

    if not razorpay_service.verify_payment_signature(
        razorpay_order_id=payload.razorpay_order_id,
        razorpay_payment_id=payload.razorpay_payment_id,
        razorpay_signature=payload.razorpay_signature,
    ):
        logger.warning(
            "Razorpay signature verification failed for order '%s'",
            order.order_number or order.id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Razorpay payment signature.",
        )

    current_status = mark_paid(db, order, payload.razorpay_payment_id)

    return PaymentVerifyResponse(
        order_id=order.id,
        order_number=order.order_number,
        amount=float(order.total_amount),
        currency=order.currency,
        payment_status="PAID",
        order_status=current_status,
        payment_reference=order.payment_reference,
        payment_timestamp=order.payment_timestamp,
    )


@router.post(
    "/{order_id}/verify-payu",
    response_model=PaymentVerifyResponse,
    summary="Verify PayU payment response directly",
)
def verify_payu_payment(
    order_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
):
    """
    Direct endpoint to verify PayU payment response data.
    Validates PayU response hash, independently verifies with PayU Postservice API,
    and marks order PAID.
    """
    if not settings.payu_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PayU payment gateway is not configured on this server.",
        )
    order = find_order(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found.",
        )

    current_status = normalize_status(order.status)
    if current_status in PAID_STATUSES or getattr(order, "payment_status", None) in ("PAID", "SUCCESS"):
        return PaymentVerifyResponse(
            order_id=order.id,
            order_number=order.order_number,
            amount=float(order.total_amount),
            currency=order.currency,
            payment_status="PAID",
            order_status=current_status,
            payment_reference=getattr(order, "payment_reference", None) or payload.get("mihpayid") or "ALREADY_PAID",
            payment_timestamp=getattr(order, "payment_timestamp", None),
        )

    if not payu_service.verify_response_hash(payload):
        logger.warning("PayU response hash verification failed for order '%s'", order.order_number or order.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid PayU payment response hash signature.",
        )

    txnid = payload.get("txnid") or getattr(order, "payment_session_id", None)
    if not txnid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transaction ID (txnid) is missing in payload.",
        )

    verification = payu_service.verify_payment_with_payu(str(txnid))
    if not verification.get("verified"):
        order.status = OrderStatus.FAILED.value
        order.payment_status = "VERIFICATION_FAILED"
        db.commit()
        record_payment_transaction(
            db=db,
            order=order,
            txnid=str(txnid),
            amount=float(order.total_amount),
            payment_gateway="PAYU",
            payment_status="VERIFICATION_FAILED",
            gateway_response=payload,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment independent verification failed with PayU: {verification.get('error') or 'Unconfirmed transaction'}",
        )

    ref = payload.get("mihpayid") or payload.get("bank_ref_num") or verification.get("mihpayid") or f"PAYU-{txnid}"
    current_status = mark_paid(db, order, reference=str(ref), payment_session_id=str(txnid))
    record_payment_transaction(
        db=db,
        order=order,
        txnid=str(txnid),
        amount=float(order.total_amount),
        mihpayid=str(ref),
        payment_gateway="PAYU",
        payment_status="SUCCESS",
        payment_mode=str(payload.get("mode") or verification.get("mode") or "UPI"),
        gateway_response=payload,
    )

    return PaymentVerifyResponse(
        order_id=order.id,
        order_number=order.order_number,
        amount=float(order.total_amount),
        currency=order.currency,
        payment_status="PAID",
        order_status=current_status,
        payment_reference=order.payment_reference,
        payment_timestamp=order.payment_timestamp,
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
    Verify payment for an order. Supports both Razorpay signature verification
    and manual / test simulation.
    """
    order = find_order(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found.",
        )

    current_status = normalize_status(order.status)

    # If already confirmed or paid, return current status idempotently
    if current_status in PAID_STATUSES or getattr(order, "payment_status", None) in ("PAID", "SUCCESS"):
        return PaymentVerifyResponse(
            order_id=order.id,
            order_number=order.order_number,
            amount=float(order.total_amount),
            currency=order.currency,
            payment_status="PAID",
            order_status=current_status,
            payment_reference=getattr(order, "payment_reference", None) or "ALREADY_PAID",
            payment_timestamp=getattr(order, "payment_timestamp", None),
        )

    if current_status in (OrderStatus.FAILED.value, OrderStatus.CANCELLED.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order '{order.order_number or order.id}' was {current_status.lower()} and cannot be verified.",
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

    # 1. Razorpay signature or payment ID provided
    if request.razorpay_signature or (request.razorpay_payment_id and not ref):
        if not razorpay_service.verify_payment_signature(
            razorpay_order_id=request.razorpay_order_id or "",
            razorpay_payment_id=request.razorpay_payment_id or "",
            razorpay_signature=request.razorpay_signature or "",
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Razorpay payment signature.",
            )
        ref = request.razorpay_payment_id or ref
        current_status = mark_paid(db, order, ref)

    # 2. Cashfree provider mode
    elif settings.effective_payment_provider == "cashfree":
        gateway_status = cashfree.fetch_payment_status(order)
        if gateway_status in cashfree.PAID_GATEWAY_STATUSES:
            if not ref:
                ref = f"CASHFREE-{cashfree.gateway_order_id(order)}"
            current_status = mark_paid(db, order, ref)
        elif gateway_status == "FAILED":
            order.status = OrderStatus.FAILED.value
            order.payment_status = "FAILED"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment failed at payment provider.",
            )
        elif gateway_status in ("CANCELLED", "USER_DROPPED"):
            order.status = OrderStatus.CANCELLED.value
            order.payment_status = "CANCELLED"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment was cancelled.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment has not been confirmed by the gateway yet.",
            )

    # 3. PayU provider mode or PayU txnid reference
    elif (
        (ref and ref.startswith("TXN-PAYU-"))
        or settings.effective_payment_provider == "payu"
    ):
        target_txnid = (
            ref
            if (ref and ref.startswith("TXN-PAYU-"))
            else str(getattr(order, "payment_session_id", "") or payu_service.generate_txnid(order))
        )
        verification = payu_service.verify_payment_with_payu(target_txnid)
        if not verification.get("verified"):
            order.status = OrderStatus.FAILED.value
            order.payment_status = "FAILED"
            db.commit()
            record_payment_transaction(
                db=db,
                order=order,
                txnid=target_txnid,
                amount=float(order.total_amount),
                payment_gateway="PAYU",
                payment_status="FAILED",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PayU payment verification failed: {verification.get('error') or 'Transaction not confirmed by PayU'}",
            )
        ref = verification.get("mihpayid") or verification.get("bank_ref_num") or target_txnid
        current_status = mark_paid(db, order, str(ref), payment_session_id=target_txnid)
        record_payment_transaction(
            db=db,
            order=order,
            txnid=target_txnid,
            amount=float(order.total_amount),
            mihpayid=str(ref),
            payment_gateway="PAYU",
            payment_status="SUCCESS",
            payment_mode=str(verification.get("mode") or "UPI"),
        )

    # 4. Direct UPI / UTR Reference or Test flow (only permitted in demo mode)
    else:
        if settings.effective_payment_provider != "demo":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manual simulation not permitted. Live payment verification must complete via payment gateway.",
            )
        if not ref:
            ref = f"UPI-KOTAK-{order.order_number or order.id[:8]}-{uuid.uuid4().hex[:6].upper()}"
        current_status = mark_paid(db, order, ref)

    return PaymentVerifyResponse(
        order_id=order.id,
        order_number=order.order_number,
        amount=float(order.total_amount),
        currency=order.currency,
        payment_status="PAID",
        order_status=normalize_status(order.status),
        payment_reference=getattr(order, "payment_reference", None) or ref,
        payment_timestamp=getattr(order, "payment_timestamp", None),
    )


@router.post("/webhook/youpi", tags=["Payments"], summary="YouPI-PG HMAC-SHA256 Webhook")
@router.post("/webhook/youpi/", include_in_schema=False)
async def youpi_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive YouPI-PG payment observation events and automatically confirm orders.
    Verifies HMAC-SHA256 signature using raw request bytes.
    Validates order ID, amount, payment ID, and UTR.
    """
    raw_body = await request.body()
    signature = (
        request.headers.get("x-gateway-signature")
        or request.headers.get("X-Gateway-Signature")
        or request.headers.get("x-signature")
        or request.headers.get("X-Signature")
        or ""
    )
    return youpi_service.process_webhook_event(
        raw_body=raw_body,
        signature_header=signature,
        db=db,
        mark_paid_func=mark_paid,
        find_order_func=find_order,
    )


@router.post("/webhook/razorpay", include_in_schema=False)
@router.post("/webhook", include_in_schema=False)
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Razorpay payment events and automatically confirm orders."""
    raw_body = await request.body()
    signature = (
        request.headers.get("x-razorpay-signature")
        or request.headers.get("X-Razorpay-Signature")
        or ""
    )

    if not razorpay_service.verify_webhook_signature(raw_body, signature):
        logger.warning("Rejected Razorpay webhook: invalid signature.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature.",
        )

    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError:
        logger.warning("Ignoring Razorpay webhook with invalid JSON payload.")
        return {"status": "ignored"}

    event = str(payload.get("event") or "").lower()
    logger.info("Received Razorpay webhook event: %s", event)

    payment_entity = (
        payload.get("payload", {}).get("payment", {}).get("entity", {})
    )
    order_entity = (
        payload.get("payload", {}).get("order", {}).get("entity", {})
    )

    notes = payment_entity.get("notes") or order_entity.get("notes") or {}
    order_identifier = (
        notes.get("order_id")
        or notes.get("order_number")
        or order_entity.get("receipt")
    )

    if not order_identifier:
        logger.warning("Razorpay webhook payload lacks order identifier in notes or receipt.")
        return {"status": "ignored"}

    order = find_order(db, str(order_identifier))
    if not order:
        logger.warning("Razorpay webhook referenced unknown order '%s'", order_identifier)
        return {"status": "ignored"}

    if event in ("payment.captured", "order.paid"):
        payment_id = payment_entity.get("id") or f"RZP-{order.order_number or order.id}"
        mark_paid(db, order, reference=str(payment_id))
        logger.info("Order %s confirmed via Razorpay webhook event: %s", order.order_number, event)
    elif event in ("payment.failed",):
        order.payment_status = "FAILED"
        db.commit()
        logger.info("Order %s marked FAILED via Razorpay webhook", order.order_number)

    return {"status": "ok"}


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
    payment_failed = "FAILED" in event_type or payment_status == "FAILED"
    payment_cancelled = "CANCELLED" in event_type or "USER_DROPPED" in event_type

    if not gateway_id:
        return {"status": "ignored"}

    order = find_order(db, gateway_id)

    if order is None:
        order = find_order(db, gateway_id.rsplit("-", 1)[0])

    if order is None:
        logger.warning("Cashfree webhook references unknown order '%s'.", gateway_id)
        return {"status": "ignored"}

    if payment_succeeded:
        ref = str(payment_info.get("cf_payment_id") or payment_info.get("bank_reference") or f"CASHFREE-{gateway_id}")
        mark_paid(db, order, ref)
    elif payment_failed:
        order.status = OrderStatus.FAILED.value
        order.payment_status = "FAILED"
        db.commit()
    elif payment_cancelled:
        order.status = OrderStatus.CANCELLED.value
        order.payment_status = "CANCELLED"
        db.commit()

    return {"status": "ok"}


@router.post("/payu/response", tags=["Payments"], summary="PayU Hosted Checkout SURL/FURL Callback")
@router.post("/payu/callback", include_in_schema=False)
@router.post("/payu/success", include_in_schema=False)
@router.post("/payu/failure", include_in_schema=False)
@router.post("/payu/webhook", include_in_schema=False)
@router.post("/webhook/payu", include_in_schema=False)
async def payu_response(request: Request, db: Session = Depends(get_db)):
    """
    Handle PayU Hosted Checkout SURL / FURL callback POST.
    1. Validates PayU response hash.
    2. Identifies order from udf1, udf2, or txnid.
    3. Handles duplicate callbacks idempotently.
    4. Independently verifies transaction with PayU Postservice API.
    5. Only verified successful payments are marked PAID and CONFIRMED.
    6. Redirects customer to frontend or returns JSON.
    """
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
    else:
        try:
            form = await request.form()
            data = dict(form)
        except Exception:
            data = {}

    if not settings.payu_configured:
        logger.error("PayU callback received but PayU credentials are not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PayU payment gateway is not configured on this server.",
        )

    txnid = str(data.get("txnid") or "").strip()
    status_raw = str(data.get("status") or "").strip().lower()
    logger.info("Received PayU callback: txnid=%s, status=%s", txnid, status_raw)

    # Validate merchant key if provided in callback
    received_key = str(data.get("key") or "").strip()
    expected_key = (settings.PAYU_MERCHANT_KEY or "").strip()
    if received_key and expected_key and received_key != expected_key:
        logger.error("Rejected PayU callback: Invalid merchant key. received=%s, expected=%s", received_key, expected_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid PayU merchant key in response.",
        )

    # STEP 7: Backend validates PayU response hash
    if not payu_service.verify_response_hash(data):
        logger.error("Rejected PayU callback: Invalid response hash. txnid=%s", txnid)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid PayU response hash signature.",
        )

    # Locate order
    order_id = str(data.get("udf1") or "").strip()
    order_num = str(data.get("udf2") or "").strip()

    order = None
    if order_id:
        order = find_order(db, order_id)
    if not order and order_num:
        order = find_order(db, order_num)
    if not order and txnid:
        order = db.query(Order).filter(Order.payment_session_id == txnid).first()

    # Look up by txnid in PaymentTransaction records (covers tablet QR flows and multi-attempt retries)
    if not order and txnid:
        txn_rec = (
            db.query(PaymentTransaction)
            .filter(PaymentTransaction.txnid == txnid)
            .order_by(PaymentTransaction.created_at.desc())
            .first()
        )
        if txn_rec and txn_rec.order_id:
            order = db.query(Order).filter(Order.id == txn_rec.order_id).first()

    mihpayid = str(data.get("mihpayid") or "").strip()
    if not order and mihpayid:
        txn_rec = (
            db.query(PaymentTransaction)
            .filter(PaymentTransaction.mihpayid == mihpayid)
            .order_by(PaymentTransaction.created_at.desc())
            .first()
        )
        if txn_rec and txn_rec.order_id:
            order = db.query(Order).filter(Order.id == txn_rec.order_id).first()

    if not order:
        logger.error("PayU callback referenced unknown order (udf1=%s, udf2=%s, txnid=%s)", order_id, order_num, txnid)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order not found for PayU transaction '{txnid}'.",
        )

    # Amount verification against order total
    raw_amount = str(data.get("amount") or "").strip()
    if raw_amount:
        try:
            paid_amount = float(raw_amount)
            expected_amount = float(order.total_amount)
            if abs(paid_amount - expected_amount) > 0.01:
                logger.error(
                    "PayU callback amount mismatch for order %s: expected %.2f, received %.2f",
                    order.order_number, expected_amount, paid_amount
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Payment amount mismatch: expected {expected_amount:.2f}, received {paid_amount:.2f}",
                )
        except ValueError:
            pass

    # Idempotency check for duplicate callbacks
    current_status = normalize_status(order.status)
    if current_status in PAID_STATUSES or getattr(order, "payment_status", None) in ("PAID", "SUCCESS"):
        logger.info("PayU callback duplicate: order %s is already paid. Returning idempotent response.", order.order_number)
        if "application/json" in request.headers.get("accept", "") or "application/json" in content_type:
            return {
                "status": "success",
                "message": "Order already paid.",
                "order_id": order.id,
                "order_number": order.order_number,
                "payment_status": "PAID",
                "order_status": current_status,
                "payment_reference": getattr(order, "payment_reference", None),
            }
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/?order_id={order.id}&payment_status=success",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    unmapped_status = str(data.get("unmappedstatus") or "").strip().lower()
    bank_ref = str(data.get("bank_ref_num") or data.get("bank_ref_no") or "").strip()
    error_msg = str(data.get("error_Message") or data.get("error") or "Payment not successful").strip()

    if status_raw != "success":
        new_status = "CANCELLED" if ("cancel" in unmapped_status or "usercancelled" in unmapped_status) else "FAILED"
        order.status = OrderStatus.CANCELLED.value if new_status == "CANCELLED" else OrderStatus.FAILED.value
        order.payment_status = new_status
        db.commit()
        if txnid:
            record_payment_transaction(
                db=db,
                order=order,
                txnid=txnid,
                amount=float(order.total_amount),
                mihpayid=mihpayid or None,
                payment_gateway="PAYU",
                payment_status=new_status,
                payment_mode=str(data.get("mode") or ""),
                gateway_response=data,
            )
        logger.info(
            "PayU transaction not successful for order %s: status=%s, unmapped=%s, error=%s",
            order.order_number, status_raw, unmapped_status, error_msg,
        )
        if "application/json" in request.headers.get("accept", "") or "application/json" in content_type:
            return {
                "status": "failed",
                "order_id": order.id,
                "order_number": order.order_number,
                "payment_status": order.payment_status,
                "order_status": order.status,
                "error": error_msg,
            }
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/?order_id={order.id}&payment_status={status_raw}&error={error_msg}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # STEP 8: Backend independently verifies payment with PayU
    verification = payu_service.verify_payment_with_payu(txnid)
    if not verification.get("verified"):
        logger.error(
            "PayU independent verification failed for order %s (txnid=%s): %s",
            order.order_number, txnid, verification,
        )
        order.status = OrderStatus.FAILED.value
        order.payment_status = "VERIFICATION_FAILED"
        db.commit()
        if txnid:
            record_payment_transaction(
                db=db,
                order=order,
                txnid=txnid,
                amount=float(order.total_amount),
                mihpayid=mihpayid or None,
                payment_gateway="PAYU",
                payment_status="VERIFICATION_FAILED",
                gateway_response=data,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment independent verification failed with PayU: {verification.get('error') or 'Unconfirmed transaction'}",
        )

    # Confirm verified amount with order total
    verified_amt = verification.get("amount")
    if verified_amt:
        try:
            v_amt = float(verified_amt)
            if abs(v_amt - float(order.total_amount)) > 0.01:
                logger.error(
                    "PayU verified amount mismatch for order %s: expected %.2f, verified %.2f",
                    order.order_number, float(order.total_amount), v_amt
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Payment verified amount mismatch: expected {float(order.total_amount):.2f}, verified {v_amt:.2f}",
                )
        except ValueError:
            pass

    # Confirm verified payment mode is strictly UPI
    mode_raw = str(data.get("mode") or verification.get("mode") or "").strip().upper()
    if mode_raw and not (mode_raw.startswith("UPI") or mode_raw in ("INTENT", "COLLECT", "QR")):
        logger.error(
            "Rejected non-UPI payment mode '%s' for order %s (UPI-only enforced)",
            mode_raw, order.order_number,
        )
        order.status = OrderStatus.FAILED.value
        order.payment_status = "NON_UPI_REJECTED"
        db.commit()
        if txnid:
            record_payment_transaction(
                db=db,
                order=order,
                txnid=txnid,
                amount=float(order.total_amount),
                mihpayid=mihpayid or None,
                payment_gateway="PAYU",
                payment_status="NON_UPI_REJECTED",
                payment_mode=mode_raw,
                gateway_response=data,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment mode '{mode_raw}' is not accepted. SmartPrint only accepts UPI payments.",
        )

    # STEP 9: Only verified successful payments are marked PAID
    ref = mihpayid or bank_ref or verification.get("mihpayid") or f"PAYU-{txnid}"
    confirmed_status = mark_paid(
        db,
        order,
        reference=ref,
        payment_session_id=txnid,
    )
    if txnid:
        record_payment_transaction(
            db=db,
            order=order,
            txnid=txnid,
            amount=float(order.total_amount),
            mihpayid=ref,
            payment_gateway="PAYU",
            payment_status="SUCCESS",
            payment_mode=str(data.get("mode") or verification.get("mode") or "UPI"),
            gateway_response=data,
        )

    logger.info(
        "PayU payment confirmed for order %s (%s) | reference: %s | status: %s",
        order.id, order.order_number, ref, confirmed_status,
    )

    if "application/json" in request.headers.get("accept", "") or "application/json" in content_type:
        return {
            "status": "success",
            "order_id": order.id,
            "order_number": order.order_number,
            "amount": float(order.total_amount),
            "currency": order.currency,
            "payment_status": "PAID",
            "order_status": confirmed_status,
            "payment_reference": order.payment_reference,
            "payment_timestamp": order.payment_timestamp,
        }

    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/?order_id={order.id}&payment_status=success",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/payu/response", tags=["Payments"], summary="PayU Return GET Redirect")
async def payu_response_get(request: Request):
    """Handle GET redirect if PayU or a browser returns to the callback URL via GET."""
    params = dict(request.query_params)
    order_id = params.get("udf1") or params.get("order_id") or ""
    status_param = params.get("status") or "success"
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/?order_id={order_id}&payment_status={status_param}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get(
    "/{order_id}/payu-checkout",
    response_class=HTMLResponse,
    summary="PayU Hosted Checkout redirect page for mobile/tablet scanning",
)
def payu_checkout_redirect(order_id: str, db: Session = Depends(get_db)):
    """
    Renders an auto-submitting HTML page that submits to PayU Hosted Checkout.
    Used when a customer scans the PayU QR fallback on the tablet or clicks a checkout link.
    """
    order = find_order(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if not settings.payu_configured:
        if settings.effective_payment_provider == "demo":
            ref = f"DEMO-{order.order_number or order.id[:8]}-{uuid.uuid4().hex[:6].upper()}"
            mark_paid(db, order, reference=ref)
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/?order_id={order.id}&payment_status=success",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PayU payment gateway is not configured on this server.",
        )

    begin_payment(db, order)
    payload = payu_service.prepare_payment_payload(order)
    txnid = payload.get("txnid")
    if txnid:
        order.payment_session_id = txnid
        db.commit()
        db.refresh(order)
        record_payment_transaction(
            db=db,
            order=order,
            txnid=txnid,
            amount=float(order.total_amount),
            payment_gateway="PAYU",
            payment_status="INITIATED",
        )

    action = payload.get("action")
    inputs = "".join(
        f'<input type="hidden" name="{k}" value="{v}">\n'
        for k, v in payload.items()
        if k != "action"
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>SmartPrint - Redirecting to PayU UPI</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #f8fafc; color: #1e293b; text-align: center; }}
        .card {{ background: white; padding: 2rem; border-radius: 1.5rem; box-shadow: 0 10px 25px rgba(0,0,0,0.05); max-width: 400px; width: 90%; border: 1px solid #e2e8f0; }}
        .spinner {{ width: 40px; height: 40px; border: 4px solid #e2e8f0; border-top-color: #059669; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 1.5rem; }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        h2 {{ margin: 0 0 0.5rem; font-size: 1.25rem; font-weight: 800; }}
        p {{ margin: 0; color: #64748b; font-size: 0.875rem; }}
        .amount {{ font-size: 1.5rem; font-weight: 900; color: #0f172a; margin: 1rem 0; }}
        button {{ margin-top: 1.5rem; width: 100%; padding: 0.75rem; border-radius: 0.75rem; background: #059669; color: white; border: none; font-weight: 700; cursor: pointer; }}
    </style>
</head>
<body onload="document.getElementById('payuForm').submit();">
    <div class="card">
        <div class="spinner"></div>
        <h2>Redirecting to PayU UPI</h2>
        <p>Order {order.order_number or order.id}</p>
        <div class="amount">₹{float(order.total_amount):.2f}</div>
        <p>Connecting to secure UPI payment gateway...</p>
        <form id="payuForm" method="POST" action="{action}">
            {inputs}
            <noscript><button type="submit">Click here to continue to PayU</button></noscript>
        </form>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)


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

    valid_unpaid = (
        OrderStatus.PAYMENT_PENDING.value,
        OrderStatus.CREATED.value,
        OrderStatus.OPTIONS_SELECTED.value,
        "PAYMENT_PENDING",
        "CREATED",
        "OPTIONS_SELECTED",
    )

    if current_status in valid_unpaid:
        session_id = getattr(order, "payment_session_id", None)
        if not session_id:
            pt = (
                db.query(PaymentTransaction)
                .filter(PaymentTransaction.order_id == order.id)
                .order_by(PaymentTransaction.created_at.desc())
                .first()
            )
            if pt and pt.txnid:
                session_id = pt.txnid

        # Check PayU transaction if order has an active PayU transaction session ID
        if session_id and str(session_id).startswith("TXN-PAYU-"):
            try:
                payu_state = payu_service.verify_payment_with_payu(str(session_id))
                if payu_state.get("verified"):
                    # Confirm verified amount
                    verified_amt = payu_state.get("amount")
                    amt_ok = True
                    if verified_amt:
                        try:
                            amt_ok = abs(float(verified_amt) - float(order.total_amount)) <= 0.01
                        except ValueError:
                            amt_ok = True
                    if amt_ok:
                        ref = payu_state.get("mihpayid") or payu_state.get("bank_ref_num") or session_id
                        current_status = mark_paid(db, order, reference=str(ref), payment_session_id=str(session_id))
                        record_payment_transaction(
                            db=db,
                            order=order,
                            txnid=str(session_id),
                            amount=float(order.total_amount),
                            mihpayid=str(ref),
                            payment_gateway="PAYU",
                            payment_status="SUCCESS",
                            payment_mode=str(payu_state.get("mode") or "UPI"),
                        )
                elif payu_state.get("status") in ("failed", "failure"):
                    order.status = OrderStatus.FAILED.value
                    order.payment_status = "FAILED"
                    db.commit()
                    current_status = OrderStatus.FAILED.value
                elif payu_state.get("status") in ("cancelled", "usercancelled"):
                    order.status = OrderStatus.CANCELLED.value
                    order.payment_status = "CANCELLED"
                    db.commit()
                    current_status = OrderStatus.CANCELLED.value
            except Exception as exc:
                logger.debug("Error checking PayU status during poll: %s", exc)

        # Check YouPI session if order has an active YouPI payment session ID
        elif session_id and not str(session_id).startswith("YOUPI-LOCAL-"):
            try:
                youpi_state = youpi_service.fetch_payment_status(order.payment_session_id)
                if youpi_state.get("isPaid"):
                    ref = youpi_state.get("utr") or order.payment_session_id
                    current_status = mark_paid(db, order, reference=ref, payment_session_id=order.payment_session_id)
                elif youpi_state.get("status") in ("FAILED",):
                    order.status = OrderStatus.FAILED.value
                    order.payment_status = "FAILED"
                    db.commit()
                    current_status = OrderStatus.FAILED.value
                elif youpi_state.get("status") in ("CANCELLED", "EXPIRED"):
                    order.status = OrderStatus.CANCELLED.value
                    order.payment_status = youpi_state.get("status")
                    db.commit()
                    current_status = OrderStatus.CANCELLED.value
            except Exception as exc:
                logger.debug("Error checking YouPI status during poll: %s", exc)

        elif settings.effective_payment_provider == "razorpay":
            order_key = str(order.order_number or order.id)
            rzp_order = razorpay_service._order_cache.get(order_key)
            if rzp_order and rzp_order.get("id"):
                payments = razorpay_service.fetch_order_payments(rzp_order["id"])
                for p in payments:
                    if p.get("status") in ("captured",):
                        current_status = mark_paid(db, order, reference=p.get("id"))
                        break
                    elif p.get("status") in ("failed",):
                        order.payment_status = "FAILED"
                        db.commit()
                        current_status = OrderStatus.FAILED.value

        elif settings.effective_payment_provider == "cashfree":
            gateway_status = cashfree.fetch_payment_status(order)

            if gateway_status in cashfree.PAID_GATEWAY_STATUSES:
                current_status = mark_paid(
                    db,
                    order,
                    f"CASHFREE-{cashfree.gateway_order_id(order)}",
                )
            elif gateway_status == "FAILED":
                order.status = OrderStatus.FAILED.value
                order.payment_status = "FAILED"
                db.commit()
                current_status = OrderStatus.FAILED.value
            elif gateway_status in ("CANCELLED", "USER_DROPPED"):
                order.status = OrderStatus.CANCELLED.value
                order.payment_status = "CANCELLED"
                db.commit()
                current_status = OrderStatus.CANCELLED.value

        elif settings.effective_payment_provider == "demo":
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
                    f"UPI-DEMO-{order.order_number or order.id[:8]}-{uuid.uuid4().hex[:6].upper()}",
                )

    upi_uri = build_dynamic_upi_uri(order)
    stored_payment_status = getattr(order, "payment_status", None)
    is_paid = current_status in PAID_STATUSES or stored_payment_status in ("PAID", "SUCCESS")
    resolved_payment_status = "PAID" if is_paid else (stored_payment_status or current_status)

    return PaymentStatusResponse(
        order_id=order.id,
        order_number=order.order_number,
        amount=float(order.total_amount),
        currency=order.currency,
        status=current_status,
        payment_status=resolved_payment_status,
        payment_reference=getattr(order, "payment_reference", None),
        payment_timestamp=getattr(order, "payment_timestamp", None),
        payment_session_id=getattr(order, "payment_session_id", None),
        upi_id=(settings.UPI_ID or "").strip(),
        upi_name=(settings.UPI_NAME or "").strip() or "SmartPrint Kiosk",
        upi_uri=upi_uri,
        is_paid=is_paid,
    )
