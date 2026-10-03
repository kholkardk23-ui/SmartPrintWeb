import uuid
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FileRecord, Order, OrderStatus
from app.schemas import OrderCreateRequest, OrderResponse, ErrorResponse
from app.services.pricing_service import (
    parse_and_validate_page_range,
    calculate_pricing,
)

logger = logging.getLogger("smartprint.orders")

router = APIRouter(prefix="/api/orders", tags=["Orders"])


# ============================================================
# GENERATE SHORT ORDER NUMBER
# ============================================================

def generate_order_number(db: Session) -> str:
    """
    Generate the next customer-facing SmartPrint order number.

    Format:
        SP-000001
        SP-000002
        SP-000003
        ...
    """

    orders = (
        db.query(Order.order_number)
        .filter(Order.order_number.isnot(None))
        .all()
    )

    highest_number = 0

    for (order_number,) in orders:
        if not order_number:
            continue

        match = re.fullmatch(r"SP-(\d+)", order_number)

        if match:
            number = int(match.group(1))
            highest_number = max(highest_number, number)

    next_number = highest_number + 1

    return f"SP-{next_number:06d}"


# ============================================================
# CREATE ORDER
# ============================================================

@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new print order",
    description=(
        "Validates print configuration, authoritatively computes "
        "sheets & price, and creates order."
    ),
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Invalid options or page range",
        },
        404: {
            "model": ErrorResponse,
            "description": "File not found",
        },
    },
)
def create_order(
    request: OrderCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Authoritative order creation endpoint:

    1. Verifies file_id exists in database.
    2. Reads actual page_count from database.
    3. Validates color mode, copies, duplex, and page range.
    4. Computes selected pages and physical sheet count.
    5. Calculates authoritative price.
    6. Generates a short customer-facing order number.
    7. Persists order with status OPTIONS_SELECTED.
    """

    # 1. Verify file exists
    file_record = (
        db.query(FileRecord)
        .filter(FileRecord.id == request.file_id)
        .first()
    )

    if not file_record:
        logger.warning(
            "Order creation failed: file_id '%s' not found.",
            request.file_id,
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{request.file_id}' not found.",
        )

    # 2. Validate color mode
    color_clean = request.color_mode.strip().lower()

    if color_clean not in ["bw", "color"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid color mode '{request.color_mode}'. "
                "Must be 'bw' or 'color'."
            ),
        )

    # 3. Parse and validate page range
    try:
        selected_pages = parse_and_validate_page_range(
            request.page_range,
            file_record.page_count,
        )

    except ValueError as err:
        logger.warning(
            "Invalid page range '%s' for file '%s': %s",
            request.page_range,
            request.file_id,
            str(err),
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )

    # 4. Calculate pricing and physical sheets
    try:
        pricing = calculate_pricing(
            selected_page_count=len(selected_pages),
            copies=request.copies,
            color_mode=color_clean,
            duplex=request.duplex,
        )

    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )

    # 5. Generate IDs
    internal_order_id = str(uuid.uuid4())
    customer_order_number = generate_order_number(db)

    # 6. Create order
    order = Order(
        id=internal_order_id,
        order_number=customer_order_number,
        file_id=file_record.id,
        copies=pricing["copies"],
        color_mode=pricing["color_mode"],
        duplex=pricing["duplex"],
        page_range=request.page_range.strip(),
        selected_page_count=pricing["selected_page_count"],
        physical_sheet_count=pricing["physical_sheet_count"],
        price_per_page=pricing["price_per_page"],
        total_amount=pricing["total_amount"],
        currency=pricing["currency"],
        status=OrderStatus.OPTIONS_SELECTED.value,
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    logger.info(
        "Created order '%s' (internal ID '%s') for file '%s': "
        "%d pages, %d copies, total %s %s",
        order.order_number,
        order.id,
        file_record.id,
        order.selected_page_count,
        order.copies,
        order.total_amount,
        order.currency,
    )

    return OrderResponse(
        order_id=order.order_number,
        file_id=order.file_id,
        filename=file_record.original_filename,
        selected_page_count=order.selected_page_count,
        copies=order.copies,
        color_mode=order.color_mode,
        duplex=order.duplex,
        page_range=order.page_range,
        physical_sheet_count=order.physical_sheet_count,
        price_per_page=float(order.price_per_page),
        total_amount=float(order.total_amount),
        currency=order.currency,
        status=order.status,
    )


# ============================================================
# GET LATEST ORDER
# ============================================================

@router.get(
    "/latest",
    response_model=OrderResponse,
    summary="Get the latest print order",
    description="Retrieves the most recently created print order.",
    responses={
        404: {
            "model": ErrorResponse,
            "description": "No orders found",
        },
    },
)
def get_latest_order(
    db: Session = Depends(get_db),
):
    """
    Retrieve the most recently created order.

    This endpoint can be used by the printer-side tablet
    to display the latest SmartPrint order.
    """

    order = (
        db.query(Order)
        .order_by(Order.created_at.desc())
        .first()
    )

    if not order:
        logger.warning(
            "Latest order lookup failed: no orders found."
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No orders found.",
        )

    filename = (
        order.file.original_filename
        if order.file
        else "document.pdf"
    )

    return OrderResponse(
        order_id=order.order_number,
        file_id=order.file_id,
        filename=filename,
        selected_page_count=order.selected_page_count,
        copies=order.copies,
        color_mode=order.color_mode,
        duplex=order.duplex,
        page_range=order.page_range,
        physical_sheet_count=order.physical_sheet_count,
        price_per_page=float(order.price_per_page),
        total_amount=float(order.total_amount),
        currency=order.currency,
        status=order.status,
    )


# ============================================================
# GET ALL ORDERS
# ============================================================

@router.get(
    "",
    response_model=list[OrderResponse],
    summary="Get all print orders",
    description="Retrieves all print orders, newest first.",
)
def get_all_orders(
    db: Session = Depends(get_db),
):
    """
    Retrieve all print orders, newest first.

    This endpoint can be used by the mobile Orders page
    and the printer-side tablet.
    """

    orders = (
        db.query(Order)
        .order_by(Order.created_at.desc())
        .all()
    )

    result = []

    for order in orders:

        filename = (
            order.file.original_filename
            if order.file
            else "document.pdf"
        )

        result.append(
            OrderResponse(
                order_id=order.order_number,
                file_id=order.file_id,
                filename=filename,
                selected_page_count=order.selected_page_count,
                copies=order.copies,
                color_mode=order.color_mode,
                duplex=order.duplex,
                page_range=order.page_range,
                physical_sheet_count=order.physical_sheet_count,
                price_per_page=float(order.price_per_page),
                total_amount=float(order.total_amount),
                currency=order.currency,
                status=order.status,
            )
        )

    return result


# ============================================================
# GET ORDER BY SHORT ORDER ID
# ============================================================

@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get order details by ID",
    description="Retrieves the complete order summary using the short SmartPrint order ID.",
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Order not found",
        },
    },
)
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve order information using the customer-facing
    short order number.

    Example:
        /api/orders/SP-000001
    """

    order = (
        db.query(Order)
        .filter(Order.order_number == order_id)
        .first()
    )

    if not order:
        logger.warning(
            "Order lookup failed: order_number '%s' not found.",
            order_id,
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID '{order_id}' not found.",
        )

    filename = (
        order.file.original_filename
        if order.file
        else "document.pdf"
    )

    return OrderResponse(
        order_id=order.order_number,
        file_id=order.file_id,
        filename=filename,
        selected_page_count=order.selected_page_count,
        copies=order.copies,
        color_mode=order.color_mode,
        duplex=order.duplex,
        page_range=order.page_range,
        physical_sheet_count=order.physical_sheet_count,
        price_per_page=float(order.price_per_page),
        total_amount=float(order.total_amount),
        currency=order.currency,
        status=order.status,
    )