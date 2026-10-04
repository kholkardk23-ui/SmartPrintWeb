import uuid
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FileRecord, Order, OrderFile, OrderStatus
from app.schemas import (
    OrderCreateRequest,
    OrderResponse,
    OrderDocumentResponse,
    ErrorResponse,
)
from app.services.pricing_service import (
    parse_and_validate_page_range,
    calculate_pricing,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["Orders"])


# ============================================================
# ORDER NUMBER GENERATOR
# ============================================================

def generate_order_number(db: Session) -> str:
    """
    Generate the next customer-facing order number.

    Format:
        SP-000001
        SP-000002
        SP-000003
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

        match = re.fullmatch(r"SP-(\d+)", order_number.strip())

        if match:
            number = int(match.group(1))
            highest_number = max(highest_number, number)

    return f"SP-{highest_number + 1:06d}"


# ============================================================
# RESPONSE HELPER
# ============================================================

def build_order_response(
    order: Order,
    db: Session,
) -> OrderResponse:
    """
    Build an OrderResponse containing all PDFs belonging
    to the order.

    Supports both:
      1. New multi-PDF orders using order_files
      2. Old single-PDF orders using orders.file_id
    """

    documents = []

    # --------------------------------------------------------
    # New multi-PDF order
    # --------------------------------------------------------

    if order.order_files:
        for order_file in order.order_files:

            file_record = (
                db.query(FileRecord)
                .filter(FileRecord.id == order_file.file_id)
                .first()
            )

            if not file_record:
                continue

            documents.append(
                OrderDocumentResponse(
                    file_id=file_record.id,
                    filename=file_record.original_filename,
                    page_count=file_record.page_count,
                    selected_page_count=order_file.selected_page_count,
                )
            )

    # --------------------------------------------------------
    # Legacy single-PDF order
    # --------------------------------------------------------

    elif order.file_id:

        file_record = (
            db.query(FileRecord)
            .filter(FileRecord.id == order.file_id)
            .first()
        )

        if file_record:

            documents.append(
                OrderDocumentResponse(
                    file_id=file_record.id,
                    filename=file_record.original_filename,
                    page_count=file_record.page_count,
                    selected_page_count=order.selected_page_count,
                )
            )

    # --------------------------------------------------------
    # File IDs
    # --------------------------------------------------------

    file_ids = [
        document.file_id
        for document in documents
    ]

    # --------------------------------------------------------
    # Return response
    # --------------------------------------------------------

    return OrderResponse(
        order_id=order.order_number,
        file_ids=file_ids,
        documents=documents,
        copies=order.copies,
        color_mode=order.color_mode,
        duplex=order.duplex,
        page_range=order.page_range,
        selected_page_count=order.selected_page_count,
        physical_sheet_count=order.physical_sheet_count,
        price_per_page=order.price_per_page,
        total_amount=order.total_amount,
        currency=order.currency,
        status=order.status,
    )


# ============================================================
# CREATE ORDER
# ============================================================

@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def create_order(
    request: OrderCreateRequest,
    db: Session = Depends(get_db),
):
    try:

        # ----------------------------------------------------
        # 1. Validate file IDs
        # ----------------------------------------------------

        if not request.file_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one PDF file is required",
            )

        # Remove duplicate file IDs while preserving order
        file_ids = list(dict.fromkeys(request.file_ids))

        # ----------------------------------------------------
        # 2. Load all files
        # ----------------------------------------------------

        file_records = []

        for file_id in file_ids:

            file_record = (
                db.query(FileRecord)
                .filter(FileRecord.id == file_id)
                .first()
            )

            if not file_record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"File not found: {file_id}",
                )

            file_records.append(file_record)

        # ----------------------------------------------------
        # 3. Validate and calculate pricing for every PDF
        # ----------------------------------------------------

        document_pricing = []

        total_selected_pages = 0
        total_physical_sheets = 0
        total_amount = 0.0

        price_per_page = None
        currency = None

        for file_record in file_records:

            # ------------------------------------------------
            # Validate page range
            # ------------------------------------------------

            try:
                selected_pages = parse_and_validate_page_range(
                    request.page_range,
                    file_record.page_count,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid page range for "
                        f"{file_record.original_filename}: {exc}"
                    ),
                )

            selected_page_count = len(selected_pages)

            # ------------------------------------------------
            # Calculate pricing for this PDF
            # ------------------------------------------------

            try:
                pricing = calculate_pricing(
                    page_count=file_record.page_count,
                    selected_page_count=selected_page_count,
                    copies=request.copies,
                    color_mode=request.color_mode,
                    duplex=request.duplex,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Pricing error for "
                        f"{file_record.original_filename}: {exc}"
                    ),
                )

            # ------------------------------------------------
            # Save pricing information
            # ------------------------------------------------

            physical_sheet_count = pricing["physical_sheet_count"]
            document_total = float(pricing["total_amount"])

            total_selected_pages += selected_page_count
            total_physical_sheets += physical_sheet_count
            total_amount += document_total

            if price_per_page is None:
                price_per_page = float(pricing["price_per_page"])

            if currency is None:
                currency = pricing["currency"]

            document_pricing.append(
                {
                    "file_record": file_record,
                    "selected_page_count": selected_page_count,
                    "physical_sheet_count": physical_sheet_count,
                    "total_amount": document_total,
                }
            )

        # ----------------------------------------------------
        # 4. Generate IDs
        # ----------------------------------------------------

        internal_order_id = str(uuid.uuid4())
        customer_order_number = generate_order_number(db)

        # ----------------------------------------------------
        # 5. Create main Order
        # ----------------------------------------------------

        order = Order(
            id=internal_order_id,
            order_number=customer_order_number,

            # Keep legacy field populated with the first PDF.
            # This preserves compatibility with older code/orders.
            file_id=file_records[0].id,

            copies=request.copies,
            color_mode=request.color_mode,
            duplex=request.duplex,
            page_range=request.page_range,

            selected_page_count=total_selected_pages,
            physical_sheet_count=total_physical_sheets,
            price_per_page=price_per_page,
            total_amount=total_amount,
            currency=currency,

            status=OrderStatus.CREATED,
        )

        db.add(order)

        # ----------------------------------------------------
        # 6. Create OrderFile rows
        # ----------------------------------------------------

        for index, item in enumerate(document_pricing):

            file_record = item["file_record"]

            order_file = OrderFile(
                id=str(uuid.uuid4()),
                order_id=internal_order_id,
                file_id=file_record.id,
                file_order=index + 1,
                selected_page_count=item["selected_page_count"],
                physical_sheet_count=item["physical_sheet_count"],
                total_amount=item["total_amount"],
            )

            db.add(order_file)

        # ----------------------------------------------------
        # 7. Commit everything together
        # ----------------------------------------------------

        db.commit()
        db.refresh(order)

        logger.info(
            "Multi-PDF order created successfully: %s | PDFs: %s | Total: %.2f %s",
            order.order_number,
            len(file_records),
            total_amount,
            currency,
        )

        # ----------------------------------------------------
        # 8. Return response
        # ----------------------------------------------------

        return build_order_response(
            order,
            db,
        )

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        logger.exception(
            "Failed to create order: %s",
            exc,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create order",
        )


# ============================================================
# GET LATEST ORDER
# ============================================================

@router.get(
    "/latest",
    response_model=OrderResponse,
)
def get_latest_order(
    db: Session = Depends(get_db),
):
    """
    Return the highest customer-facing order number.

    Example:
        SP-000006
    """

    order = (
        db.query(Order)
        .filter(Order.order_number.isnot(None))
        .order_by(Order.order_number.desc())
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No orders found",
        )

    return build_order_response(
        order,
        db,
    )


# ============================================================
# GET ALL ORDERS
# ============================================================

@router.get(
    "",
    response_model=list[OrderResponse],
)
def get_all_orders(
    db: Session = Depends(get_db),
):
    """
    Return ALL orders.

    Highest order number is ALWAYS FIRST.

    Example:

        SP-000006
        SP-000005
        SP-000004
        SP-000003
        SP-000002
        SP-000001
    """

    orders = (
        db.query(Order)
        .filter(Order.order_number.isnot(None))
        .order_by(Order.order_number.desc())
        .all()
    )

    return [
        build_order_response(order, db)
        for order in orders
    ]


# ============================================================
# GET ORDER BY ORDER NUMBER
# ============================================================

@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    responses={
        404: {"model": ErrorResponse},
    },
)
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
):
    """
    Get one order using customer-facing order number.

    Example:
        /api/orders/SP-000006
    """

    order = (
        db.query(Order)
        .filter(Order.order_number == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return build_order_response(
        order,
        db,
    )