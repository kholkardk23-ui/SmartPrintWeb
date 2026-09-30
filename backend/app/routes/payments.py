import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Order, OrderStatus
from app.schemas import (
    PaymentStartResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
)

logger = logging.getLogger("smartprint.payments")

router = APIRouter(prefix="/api/payments", tags=["Payments"])


@router.post(
    "/{order_id}/start",
    response_model=PaymentStartResponse,
    summary="Start payment for an order",
)
def start_payment(order_id: str, db: Session = Depends(get_db)):
    """
    Start the payment process for an existing print order.

    The order must currently be in OPTIONS_SELECTED state.
    The backend changes it to PAYMENT_PENDING.

    This endpoint does NOT confirm that money has been received.
    """

    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID '{order_id}' not found.",
        )

    # Payment can only start for a newly configured order.
    if order.status != OrderStatus.OPTIONS_SELECTED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Payment cannot be started for order '{order_id}' "
                f"because its current status is '{order.status}'."
            ),
        )

    # Payment must be explicitly enabled before the machine can accept it.
    if not settings.PAYMENT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment system is currently disabled.",
        )

    order.status = OrderStatus.PAYMENT_PENDING.value

    db.commit()
    db.refresh(order)

    logger.info(
        "Payment started for order '%s': %s %s",
        order.id,
        order.total_amount,
        order.currency,
    )

    return PaymentStartResponse(
        order_id=order.id,
        amount=float(order.total_amount),
        currency=order.currency,
        payment_status="PAYMENT_PENDING",
        upi_id=settings.UPI_ID,
        upi_name=settings.UPI_NAME,
    )


@router.post(
    "/{order_id}/verify",
    response_model=PaymentVerifyResponse,
    summary="Verify payment for an order",
)
def verify_payment(
    order_id: str,
    request: PaymentVerifyRequest,
    db: Session = Depends(get_db),
):
    """
    DEMO payment verification endpoint.

    This endpoint is intentionally a simulation for development/testing.

    It accepts a payment reference and changes the order from
    PAYMENT_PENDING to PAID.

    IMPORTANT:
    This does NOT verify an actual UPI transaction.
    A real payment gateway/API must replace this logic before production use.
    """

    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID '{order_id}' not found.",
        )

    if order.status != OrderStatus.PAYMENT_PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Payment verification requires PAYMENT_PENDING status. "
                f"Current status is '{order.status}'."
            ),
        )

    payment_reference = request.payment_reference.strip()

    if not payment_reference:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment reference cannot be empty.",
        )

    # DEMO ONLY:
    # We are not contacting a bank or UPI provider yet.
    order.status = OrderStatus.PAID.value

    db.commit()
    db.refresh(order)

    logger.info(
        "DEMO payment verified for order '%s' using reference '%s'",
        order.id,
        payment_reference,
    )

    return PaymentVerifyResponse(
        order_id=order.id,
        amount=float(order.total_amount),
        currency=order.currency,
        payment_status="PAID",
        order_status=order.status,
    )