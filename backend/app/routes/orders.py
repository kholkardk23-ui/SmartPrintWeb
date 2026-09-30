import uuid
import logging
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


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new print order",
    description="Validates print configuration, authoritatively computes sheets & price, and creates order.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid options or page range"},
        404: {"model": ErrorResponse, "description": "File not found"},
    },
)
def create_order(request: OrderCreateRequest, db: Session = Depends(get_db)):
    """
    Authoritative order creation endpoint:
    1. Verifies file_id exists in database.
    2. Reads actual page_count from database.
    3. Validates color mode, copies, duplex, and page range.
    4. Computes selected pages and physical sheet count.
    5. Calculates authoritative price.
    6. Persists order in MySQL with status OPTIONS_SELECTED.
    """
    # 1. Verify file exists
    file_record = db.query(FileRecord).filter(FileRecord.id == request.file_id).first()
    if not file_record:
        logger.warning("Order creation failed: file_id '%s' not found.", request.file_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{request.file_id}' not found.",
        )

    # 2. Validate color mode
    color_clean = request.color_mode.strip().lower()
    if color_clean not in ["bw", "color"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid color mode '{request.color_mode}'. Must be 'bw' or 'color'.",
        )

    # 3. Parse and validate page range against authoritative page count
    try:
        selected_pages = parse_and_validate_page_range(
            request.page_range, file_record.page_count
        )
    except ValueError as err:
        logger.warning("Invalid page range '%s' for file '%s': %s", request.page_range, request.file_id, str(err))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )

    # 4. Authoritatively calculate pricing and sheets
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

    # 5. Create Order in database
    order_id = str(uuid.uuid4())
    order = Order(
        id=order_id,
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
        "Created order '%s' for file '%s': %d pages, %d copies, total %s %s",
        order.id,
        file_record.id,
        order.selected_page_count,
        order.copies,
        order.total_amount,
        order.currency,
    )

    return OrderResponse(
        order_id=order.id,
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


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get order details by ID",
    description="Retrieves the complete order summary for a given order ID.",
    responses={
        404: {"model": ErrorResponse, "description": "Order not found"},
    },
)
def get_order(order_id: str, db: Session = Depends(get_db)):
    """
    Retrieve order information by order_id:
    Returns complete order summary including filename, selected pages, copies, and total amount.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        logger.warning("Order lookup failed: order_id '%s' not found.", order_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID '{order_id}' not found.",
        )

    filename = order.file.original_filename if order.file else "document.pdf"

    return OrderResponse(
        order_id=order.id,
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
