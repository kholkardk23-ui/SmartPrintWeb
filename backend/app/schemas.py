from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# HEALTH
# ============================================================

class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(
        ...,
        json_schema_extra={"example": "ok"}
    )

    service: str = Field(
        ...,
        json_schema_extra={"example": "SmartPrint Backend"}
    )

    database: Optional[str] = Field(
        default="connected",
        json_schema_extra={"example": "connected"}
    )


# ============================================================
# FILE UPLOAD
# ============================================================

class FileUploadResponse(BaseModel):
    """Response returned upon successful file upload."""

    model_config = ConfigDict(from_attributes=True)

    file_id: str
    original_filename: str
    file_size: int
    page_count: int
    status: str


# ============================================================
# ERROR
# ============================================================

class ErrorResponse(BaseModel):
    """Generic error response schema."""

    detail: str


# ============================================================
# ORDER CREATE
# ============================================================

class OrderCreateRequest(BaseModel):
    """
    Request schema for creating a print order.

    One order can contain multiple PDF files.
    """

    file_ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of uploaded PDF file UUIDs",
        json_schema_extra={
            "example": [
                "7ba3d865-4e56-4552-9708-87c71dd6e14a",
                "5bced4ea-7eb1-419c-9442-99452eec7e62"
            ]
        }
    )

    copies: int = Field(
        1,
        ge=1,
        le=100,
        description="Number of copies (1-100)"
    )

    color_mode: str = Field(
        "bw",
        description="Color mode ('bw' or 'color')"
    )

    duplex: bool = Field(
        False,
        description="Duplex printing (False=single side, True=double side)"
    )

    page_range: str = Field(
        "all",
        description="Page range ('all' or e.g. '1-3, 5, 7-9')"
    )


# ============================================================
# ORDER DOCUMENT
# ============================================================

class OrderDocumentResponse(BaseModel):
    """
    Information about one PDF inside an order.
    """

    file_id: str
    filename: str
    page_count: int
    selected_page_count: int


# ============================================================
# ORDER RESPONSE
# ============================================================

class OrderResponse(BaseModel):
    """
    Response returned for a SmartPrint order.

    Supports multiple PDFs in one order.
    """

    model_config = ConfigDict(from_attributes=True)

    # Customer-facing order number
    order_id: str

    # All PDF IDs in this order
    file_ids: List[str]

    # Detailed information for every PDF
    documents: List[OrderDocumentResponse]

    # Printing options
    copies: int
    color_mode: str
    duplex: bool
    page_range: str

    # Combined totals for the complete order
    selected_page_count: int
    physical_sheet_count: int

    # Pricing
    price_per_page: float
    total_amount: float
    currency: str

    # Current order status
    status: str


# ============================================================
# PAYMENT START
# ============================================================

class PaymentStartResponse(BaseModel):
    """Response returned when payment is started for an order."""

    order_id: str
    amount: float
    currency: str
    payment_status: str
    upi_id: str
    upi_name: str


# ============================================================
# PAYMENT VERIFY REQUEST
# ============================================================

class PaymentVerifyRequest(BaseModel):
    """Request used to verify a payment."""

    payment_reference: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Payment transaction/reference ID"
    )


# ============================================================
# PAYMENT VERIFY RESPONSE
# ============================================================

class PaymentVerifyResponse(BaseModel):
    """Response returned after payment verification."""

    order_id: str
    amount: float
    currency: str
    payment_status: str
    order_status: str


# ============================================================
# PRINTER CREATE
# ============================================================

class PrinterCreateRequest(BaseModel):
    """Request schema for registering a SmartPrint printer."""

    machine_code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Unique machine code, e.g. SP-001"
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable printer name"
    )


# ============================================================
# PRINTER RESPONSE
# ============================================================

class PrinterResponse(BaseModel):
    """Response schema for a registered SmartPrint printer."""

    model_config = ConfigDict(from_attributes=True)

    printer_id: str
    machine_code: str
    name: str
    is_active: bool