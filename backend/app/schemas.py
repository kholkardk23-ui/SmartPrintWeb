from typing import Optional, List, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    Supports both multiple PDF files via file_ids and legacy single file_id.
    """

    file_ids: Optional[List[str]] = Field(
        default=None,
        description="List of uploaded PDF file UUIDs",
        json_schema_extra={
            "example": [
                "7ba3d865-4e56-4552-9708-87c71dd6e14a",
                "5bced4ea-7eb1-419c-9442-99452eec7e62"
            ]
        }
    )

    file_id: Optional[str] = Field(
        default=None,
        description="Single uploaded PDF file UUID for backwards compatibility",
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

    @model_validator(mode="before")
    @classmethod
    def unify_file_ids(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if not values.get("file_ids") and values.get("file_id"):
                values["file_ids"] = [values["file_id"]]
            elif values.get("file_ids") is None:
                values["file_ids"] = []
        return values


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

    # Customer-facing order number and UUID
    id: Optional[str] = None
    order_id: str
    order_number: Optional[str] = None

    # Legacy fields for single-file backwards compatibility
    file_id: Optional[str] = None
    filename: Optional[str] = None

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
    """Response returned when dynamic UPI payment is started for an order."""

    order_id: str
    order_number: Optional[str] = None
    amount: float
    currency: str
    payment_status: str
    upi_id: str
    upi_name: str
    upi_uri: str
    qr_data: str


# ============================================================
# PAYMENT VERIFY REQUEST
# ============================================================

class PaymentVerifyRequest(BaseModel):
    """Request used to verify a payment."""

    payment_reference: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Payment transaction/reference ID (e.g. UTR). Auto-generated if omitted in demo mode.",
    )


# ============================================================
# PAYMENT VERIFY RESPONSE
# ============================================================

class PaymentVerifyResponse(BaseModel):
    """Response returned after payment verification."""

    order_id: str
    order_number: Optional[str] = None
    amount: float
    currency: str
    payment_status: str
    order_status: str
    payment_reference: Optional[str] = None


# ============================================================
# PAYMENT CHECKOUT (AUTOMATIC VERIFICATION)
# ============================================================

class PaymentCheckoutResponse(BaseModel):
    """Session information used to collect an automatic UPI payment."""

    order_id: str
    order_number: Optional[str] = None
    amount: float
    currency: str

    # "cashfree" -> open the Cashfree checkout with payment_session_id
    # "demo"     -> no gateway; the backend confirms the payment automatically
    provider: str
    mode: str

    payment_session_id: Optional[str] = None
    checkout_url: Optional[str] = None

    upi_id: str
    upi_name: str
    upi_uri: Optional[str] = None
    qr_data: Optional[str] = None

    auto_verify_seconds: Optional[int] = None
    status: str
    message: str


# ============================================================
# PAYMENT STATUS RESPONSE
# ============================================================

class PaymentStatusResponse(BaseModel):
    """Response returned for payment status query."""

    order_id: str
    order_number: Optional[str] = None
    amount: float
    currency: str
    status: str
    payment_status: str
    upi_id: str
    upi_name: str
    upi_uri: Optional[str] = None
    is_paid: bool


# ============================================================
# ORDER STATUS UPDATE
# ============================================================

class OrderStatusUpdateRequest(BaseModel):
    """Request to update order status."""

    status: str = Field(..., description="Target order status, e.g. PRINTING, COMPLETED")


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