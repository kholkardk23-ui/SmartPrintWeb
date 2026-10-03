import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


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


class FileRecord(Base):
    """File record model storing uploaded document metadata."""

    __tablename__ = "files"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True)
    file_size = Column(Integer, nullable=False)  # in bytes
    page_count = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False, default="uploaded")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<FileRecord(id='{self.id}', filename='{self.original_filename}', pages={self.page_count})>"


class Order(Base):
    """Order model storing customer print configuration, calculated sheets, and authoritative price."""

    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_number = Column(String(20), nullable=False, unique=True, index=True)
    file_id = Column(String(36), ForeignKey("files.id"), nullable=False, index=True)
    copies = Column(Integer, nullable=False, default=1)
    color_mode = Column(String(20), nullable=False, default="bw")  # 'bw' or 'color'
    duplex = Column(Boolean, nullable=False, default=False)  # False: single side, True: double side
    page_range = Column(String(100), nullable=False, default="all")
    selected_page_count = Column(Integer, nullable=False)
    physical_sheet_count = Column(Integer, nullable=False)
    price_per_page = Column(Numeric(10, 2), nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="INR")
    status = Column(String(50), nullable=False, default=OrderStatus.OPTIONS_SELECTED.value)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    file = relationship("FileRecord", backref="orders")

    def __repr__(self) -> str:
        return f"<Order(id='{self.id}', file_id='{self.file_id}', amount={self.total_amount} {self.currency})>"

class Printer(Base):
    """Physical SmartPrint machine registered with the backend."""

    __tablename__ = "printers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    machine_code = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<Printer(id='{self.id}', "
            f"machine_code='{self.machine_code}', "
            f"name='{self.name}', active={self.is_active})>"
        )
class PrinterSession(Base):
    """Session linking a customer upload to a specific SmartPrint printer."""

    __tablename__ = "printer_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
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
    status = Column(String(50), nullable=False, default="WAITING_FOR_UPLOAD")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    printer = relationship("Printer", backref="sessions")
    file = relationship("FileRecord", backref="sessions")

    def __repr__(self) -> str:
        return (
            f"<PrinterSession(id='{self.id}', "
            f"printer_id='{self.printer_id}', "
            f"file_id='{self.file_id}', "
            f"status='{self.status}')>"
        )