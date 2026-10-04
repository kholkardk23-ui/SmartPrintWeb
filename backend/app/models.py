import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Boolean,
    Numeric,
    ForeignKey,
)

from sqlalchemy.orm import relationship

from app.database import Base


# ============================================================
# ORDER STATUS
# ============================================================

class OrderStatus(str, enum.Enum):
    """Enumeration of lifecycle statuses for a print order."""

    CREATED = "CREATED"
    OPTIONS_SELECTED = "OPTIONS_SELECTED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    QUEUED = "QUEUED"
    PRINTING = "PRINTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ============================================================
# FILE RECORD
# ============================================================

class FileRecord(Base):
    """File record model storing uploaded document metadata."""

    __tablename__ = "files"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    original_filename = Column(
        String(255),
        nullable=False,
    )

    stored_filename = Column(
        String(255),
        nullable=False,
        unique=True,
    )

    file_size = Column(
        Integer,
        nullable=False,
    )

    page_count = Column(
        Integer,
        nullable=False,
    )

    status = Column(
        String(50),
        nullable=False,
        default="uploaded",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationship to multi-file orders
    order_files = relationship(
        "OrderFile",
        back_populates="file",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<FileRecord("
            f"id='{self.id}', "
            f"filename='{self.original_filename}', "
            f"pages={self.page_count}"
            f")>"
        )


# ============================================================
# ORDER
# ============================================================

class Order(Base):
    """
    Order model.

    The old file_id column is intentionally kept for compatibility
    with existing single-PDF orders.

    New multi-PDF orders use the OrderFile table.
    """

    __tablename__ = "orders"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    order_number = Column(
        String(20),
        nullable=False,
        unique=True,
        index=True,
    )

    # --------------------------------------------------------
    # Legacy single-file field
    # --------------------------------------------------------
    # KEEP THIS so existing orders continue to work.
    file_id = Column(
        String(36),
        ForeignKey("files.id"),
        nullable=False,
        index=True,
    )

    copies = Column(
        Integer,
        nullable=False,
        default=1,
    )

    color_mode = Column(
        String(20),
        nullable=False,
        default="bw",
    )

    duplex = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    page_range = Column(
        String(100),
        nullable=False,
        default="all",
    )

    selected_page_count = Column(
        Integer,
        nullable=False,
    )

    physical_sheet_count = Column(
        Integer,
        nullable=False,
    )

    price_per_page = Column(
        Numeric(10, 2),
        nullable=False,
    )

    total_amount = Column(
        Numeric(10, 2),
        nullable=False,
    )

    currency = Column(
        String(10),
        nullable=False,
        default="INR",
    )

    status = Column(
        String(50),
        nullable=False,
        default=OrderStatus.OPTIONS_SELECTED.value,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # --------------------------------------------------------
    # Legacy relationship
    # --------------------------------------------------------

    file = relationship(
        "FileRecord",
        foreign_keys=[file_id],
    )

    # --------------------------------------------------------
    # NEW: Multiple PDFs belonging to this order
    # --------------------------------------------------------

    order_files = relationship(
        "OrderFile",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderFile.file_order",
    )

    def __repr__(self) -> str:
        return (
            f"<Order("
            f"id='{self.id}', "
            f"order_number='{self.order_number}', "
            f"amount={self.total_amount} {self.currency}"
            f")>"
        )


# ============================================================
# ORDER FILE
# ============================================================

class OrderFile(Base):
    """
    Links multiple uploaded PDFs to one print order.

    Example:

        Order SP-000025
            |
            +-- file 1
            +-- file 2
            +-- file 3

    file_order controls the printing order.
    """

    __tablename__ = "order_files"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    order_id = Column(
        String(36),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    file_id = Column(
        String(36),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Position of the PDF inside the order.
    # 1 = first PDF
    # 2 = second PDF
    # 3 = third PDF
    file_order = Column(
        Integer,
        nullable=False,
        default=1,
    )

    # Number of selected pages for this document.
    selected_page_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    # Number of physical sheets required for this document.
    physical_sheet_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    # Price calculated for this document.
    total_amount = Column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    order = relationship(
        "Order",
        back_populates="order_files",
    )

    file = relationship(
        "FileRecord",
        back_populates="order_files",
    )

    def __repr__(self) -> str:
        return (
            f"<OrderFile("
            f"id='{self.id}', "
            f"order_id='{self.order_id}', "
            f"file_id='{self.file_id}', "
            f"order={self.file_order}"
            f")>"
        )


# ============================================================
# PRINTER
# ============================================================

class Printer(Base):
    """Physical SmartPrint machine registered with the backend."""

    __tablename__ = "printers"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    machine_code = Column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    name = Column(
        String(100),
        nullable=False,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Printer("
            f"id='{self.id}', "
            f"machine_code='{self.machine_code}', "
            f"name='{self.name}', "
            f"active={self.is_active}"
            f")>"
        )


# ============================================================
# PRINTER SESSION
# ============================================================

class PrinterSession(Base):
    """
    Session linking a customer upload to a specific
    SmartPrint printer.
    """

    __tablename__ = "printer_sessions"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    printer_id = Column(
        String(36),
        ForeignKey("printers.id"),
        nullable=False,
        index=True,
    )

    file_id = Column(
        String(36),
        ForeignKey("files.id"),
        nullable=True,
        index=True,
    )

    status = Column(
        String(50),
        nullable=False,
        default="WAITING_FOR_UPLOAD",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    printer = relationship(
        "Printer",
        backref="sessions",
    )

    file = relationship(
        "FileRecord",
        backref="sessions",
    )

    def __repr__(self) -> str:
        return (
            f"<PrinterSession("
            f"id='{self.id}', "
            f"printer_id='{self.printer_id}', "
            f"file_id='{self.file_id}', "
            f"status='{self.status}'"
            f")>"
        )