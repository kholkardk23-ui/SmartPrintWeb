from fastapi import APIRouter
from app.schemas import HealthResponse
from app.database import check_database_health

router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def get_health():
    """Health check endpoint to verify backend service and database connectivity."""
    db_ok = check_database_health()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        service="SmartPrint Backend",
        database="connected" if db_ok else "disconnected",
    )
