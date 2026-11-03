import uuid
import logging
import re
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FileRecord, Order, OrderFile, OrderStatus
from app.schemas import (
    OrderCreateRequest,
    OrderResponse,
    OrderDocumentResponse,
    OrderStatusUpdateRequest,
    ErrorResponse,
)
from app.services.pricing_service import (
    parse_and_validate_page_range,
    calculate_pricing,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["Orders"])


# ============================================================
# STATUS HELPERS
# ============================================================

def normalize_status(value) -> str:
    """Return the plain status value for enums and legacy stored values.

    Older rows may contain values such as "OrderStatus.CREATED" because an
    enum member was assigned directly to the string column. Normalizing here
    keeps those rows usable without a database migration.
    """

    if isinstance(value, OrderStatus):
        return value.value

    raw = str(value or "").strip()

    if raw.startswith("OrderStatus."):
        return raw.split(".", 1)[1]

    return raw


# ============================================================
# ORDER NUMBER GENERATOR
# ============================================================

def generate_order_number(db: Session) -> str:
    """
    Generate the next customer-facing order number.

    Examples:
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

        match = re.fullmatch(
            r"SP-(\d+)",
            order_number.strip(),
        )

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

    Supports:
        1. Multi-PDF orders using order_files.
        2. Legacy single-PDF orders using orders.file_id.
    """

    documents = []

    # Multi-PDF order
    if order.order_files:
        sorted_order_files = sorted(
            order.order_files,
            key=lambda item: (
                item.file_order
                if item.file_order is not None
                else 0
            ),
        )

        for order_file in sorted_order_files:
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
                    selected_page_count=(
                        order_file.selected_page_count
                    ),
                )
            )

    # Legacy single-PDF order
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
                    selected_page_count=(
                        order.selected_page_count
                    ),
                )
            )

    file_ids = [
        document.file_id
        for document in documents
    ]

    primary_file_id = documents[0].file_id if documents else order.file_id
    primary_filename = documents[0].filename if documents else None

    norm_status = normalize_status(order.status)
    stored_payment_status = getattr(order, "payment_status", None)
    is_paid = (
        norm_status in ("CONFIRMED", "PAID", "QUEUED", "PRINTING", "COMPLETED")
        or stored_payment_status in ("PAID", "SUCCESS")
    )
    resolved_payment_status = "PAID" if is_paid else (stored_payment_status or "PENDING")

    return OrderResponse(
        id=order.id,
        order_id=order.order_number,
        order_number=order.order_number,
        file_id=primary_file_id,
        filename=primary_filename,
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
        status=norm_status,
        payment_status=resolved_payment_status,
        payment_reference=getattr(order, "payment_reference", None),
        payment_timestamp=getattr(order, "payment_timestamp", None),
        is_paid=is_paid,
        created_at=order.created_at,
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
        # 1. Validate file IDs
        if not request.file_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one PDF file is required",
            )

        # Remove duplicate IDs while preserving order
        file_ids = list(dict.fromkeys(request.file_ids))

        # 2. Load all files
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

        # 3. Calculate pricing for every PDF
        document_pricing = []

        total_selected_pages = 0
        total_physical_sheets = 0
        total_amount = 0.0

        price_per_page = None
        currency = None

        for file_record in file_records:

            # Validate page range for this PDF
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
                ) from exc

            selected_page_count = len(selected_pages)

            # Calculate document pricing
            try:
                pricing = calculate_pricing(
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
                ) from exc

            physical_sheet_count = pricing[
                "physical_sheet_count"
            ]

            document_total = float(
                pricing["total_amount"]
            )

            total_selected_pages += selected_page_count
            total_physical_sheets += physical_sheet_count
            total_amount += document_total

            if price_per_page is None:
                price_per_page = float(
                    pricing["price_per_page"]
                )

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

        # Check for existing duplicate pending order
        cutoff_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=15)
        existing_pending = (
            db.query(Order)
            .filter(
                Order.created_at >= cutoff_time,
                Order.status.in_([
                    OrderStatus.CREATED.value,
                    OrderStatus.OPTIONS_SELECTED.value,
                    OrderStatus.PAYMENT_PENDING.value,
                    "CREATED",
                    "OPTIONS_SELECTED",
                    "PAYMENT_PENDING",
                ]),
                Order.copies == request.copies,
                Order.color_mode == request.color_mode,
                Order.duplex == request.duplex,
                Order.page_range == request.page_range,
            )
            .order_by(Order.created_at.desc())
            .all()
        )

        for candidate in existing_pending:
            cand_files = (
                [of.file_id for of in candidate.order_files]
                if candidate.order_files
                else ([candidate.file_id] if candidate.file_id else [])
            )
            if cand_files == file_ids:
                logger.info(
                    "Reusing existing pending order %s to prevent duplicate order",
                    candidate.order_number or candidate.id,
                )
                return build_order_response(candidate, db)

        # 4. Generate IDs and customer-facing order number
        internal_order_id = str(uuid.uuid4())

        customer_order_number = generate_order_number(db)

        # 5. Create main order
        order = Order(
            id=internal_order_id,
            order_number=customer_order_number,
            file_id=file_records[0].id,
            copies=request.copies,
            color_mode=request.color_mode,
            duplex=request.duplex,
            page_range=request.page_range,
            selected_page_count=total_selected_pages,
            physical_sheet_count=total_physical_sheets,
            price_per_page=price_per_page,
            total_amount=round(total_amount, 2),
            currency=currency,
            status=OrderStatus.CREATED.value,
            payment_status="PENDING",
        )

        db.add(order)

        # 6. Create OrderFile rows for every PDF
        for index, item in enumerate(document_pricing):

            file_record = item["file_record"]

            order_file = OrderFile(
                id=str(uuid.uuid4()),
                order_id=internal_order_id,
                file_id=file_record.id,
                file_order=index + 1,
                selected_page_count=(
                    item["selected_page_count"]
                ),
                physical_sheet_count=(
                    item["physical_sheet_count"]
                ),
                total_amount=item["total_amount"],
            )

            db.add(order_file)

        # 7. Save order and associated documents together
        db.commit()
        db.refresh(order)

        logger.info(
            (
                "Multi-PDF order created successfully: %s | "
                "PDFs: %s | Total: %.2f %s"
            ),
            order.order_number,
            len(file_records),
            total_amount,
            currency,
        )

        # 8. Return order response
        return build_order_response(order, db)

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
        ) from exc


# ============================================================
# GET LATEST ORDER
# ============================================================

@router.get(
    "/latest",
    response_model=OrderResponse,
)
def get_latest_order(
    confirmed_only: bool = False,
    db: Session = Depends(get_db),
):
    """
    Return the latest order by customer-facing order number.
    """
    query = db.query(Order).filter(Order.order_number.isnot(None))
    if confirmed_only:
        query = query.filter(
            (Order.status.in_(["CONFIRMED", "PAID", "QUEUED", "PRINTING", "COMPLETED"]))
            | (Order.payment_status.in_(["PAID", "SUCCESS"]))
        )

    order = query.order_by(Order.order_number.desc()).first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No orders found",
        )

    return build_order_response(order, db)


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
    Return all orders in descending order-number order.
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
    Get an order using its customer-facing order number.

    Example:
        /api/orders/SP-000006
    """

    order = (
        db.query(Order)
        .filter((Order.order_number == order_id) | (Order.id == order_id))
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return build_order_response(order, db)


# ============================================================
# UPDATE ORDER STATUS
# ============================================================

@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse,
    responses={
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
    },
)
def update_order_status(
    order_id: str,
    payload: OrderStatusUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Update the lifecycle status of an order (e.g. PRINTING, COMPLETED).
    """
    order = (
        db.query(Order)
        .filter((Order.order_number == order_id) | (Order.id == order_id))
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    target_status = payload.status.strip().upper()
    valid_statuses = [s.value for s in OrderStatus]

    if target_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{payload.status}'. Valid statuses: {valid_statuses}",
        )

    order.status = target_status
    db.commit()
    db.refresh(order)

    logger.info("Order '%s' status updated to '%s'", order.order_number or order.id, target_status)
    return build_order_response(order, db)
