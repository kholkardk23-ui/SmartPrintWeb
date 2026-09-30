import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Printer
from app.schemas import PrinterCreateRequest, PrinterResponse


router = APIRouter(
    prefix="/api/printers",
    tags=["Printers"],
)


@router.post(
    "",
    response_model=PrinterResponse,
    status_code=201,
)
def create_printer(
    request: PrinterCreateRequest,
    db: Session = Depends(get_db),
):
    """Register a new SmartPrint printer."""

    existing_printer = (
        db.query(Printer)
        .filter(Printer.machine_code == request.machine_code)
        .first()
    )

    if existing_printer:
        raise HTTPException(
            status_code=409,
            detail="A printer with this machine code already exists.",
        )

    printer = Printer(
        id=str(uuid.uuid4()),
        machine_code=request.machine_code,
        name=request.name,
        is_active=True,
    )

    db.add(printer)
    db.commit()
    db.refresh(printer)

    return PrinterResponse(
        printer_id=printer.id,
        machine_code=printer.machine_code,
        name=printer.name,
        is_active=printer.is_active,
    )


@router.get(
    "/{machine_code}",
    response_model=PrinterResponse,
)
def get_printer(
    machine_code: str,
    db: Session = Depends(get_db),
):
    """Get a printer using its unique machine code."""

    printer = (
        db.query(Printer)
        .filter(Printer.machine_code == machine_code)
        .first()
    )

    if not printer:
        raise HTTPException(
            status_code=404,
            detail="Printer not found.",
        )

    return PrinterResponse(
        printer_id=printer.id,
        machine_code=printer.machine_code,
        name=printer.name,
        is_active=printer.is_active,
    )