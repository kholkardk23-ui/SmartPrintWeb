from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(..., json_schema_extra={"example": "ok"})
    service: str = Field(..., json_schema_extra={"example": "SmartPrint Backend"})
    database: Optional[str] = Field(
        default="connected",
        json_schema_extra={"example": "connected"}
    )


class FileUploadResponse(BaseModel):
    """Response returned upon successful file upload."""
    model_config = ConfigDict(from_attributes=True)

    file_id: str
    original_filename: str
    file_size: int
    page_count: int
    status: str


class ErrorResponse(BaseModel):
    """Generic error response schema."""
    detail: str


class OrderCreateRequest(BaseModel):
    """Request schema for creating a new print order."""
    file_id: str = Field(
        ...,
        description="UUID of the uploaded file",
        min_length=1
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


class OrderResponse(BaseModel):
    """Authoritative order response schema."""
    model_config = ConfigDict(from_attributes=True)

    order_id: str
    file_id: str
    filename: str
    selected_page_count: int
    copies: int
    color_mode: str
    duplex: bool
    page_range: str
    physical_sheet_count: int
    price_per_page: float
    total_amount: float
    currency: str
    status: str


class PaymentStartResponse(BaseModel):
    """Response returned when payment is started for an order."""
    order_id: str
    amount: float
    currency: str
    payment_status: str
    upi_id: str
    upi_name: str


class PaymentVerifyRequest(BaseModel):
    """Request used to verify a payment."""
    payment_reference: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Payment transaction/reference ID"
    )


class PaymentVerifyResponse(BaseModel):
    """Response returned after payment verification."""
    order_id: str
    amount: float
    currency: str
    payment_status: str
    order_status: str
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


class PrinterResponse(BaseModel):
    """Response schema for a registered SmartPrint printer."""

    model_config = ConfigDict(from_attributes=True)

    printer_id: str
    machine_code: str
    name: str
    is_active: bool