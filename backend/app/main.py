import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base, verify_database_connection, DatabaseConnectionError
from app.routes import health, files, orders, payments, printers, sessions

logger = logging.getLogger("smartprint.main")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: verify MySQL database connectivity and initialize tables on startup."""
    logger.info("Initializing SmartPrint backend...")
    try:
        verify_database_connection()
        Base.metadata.create_all(bind=engine)
        logger.info("Successfully connected to MySQL database and verified tables.")
    except DatabaseConnectionError as err:
        logger.error("Database initialization failed: %s", str(err))
        # Keep application running so health check can report 'degraded' and docs are accessible,
        # but log the clear error without credentials.
    yield
    logger.info("Shutting down SmartPrint backend.")


app = FastAPI(
    title="SmartPrint API",
    description="Backend API for SmartPrint Self-Service Printing Kiosk System (MySQL)",
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(files.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(printers.router)
app.include_router(sessions.router)

@app.get("/", tags=["Root"])
def root():
    """Root redirect / information endpoint."""
    return {
        "message": "Welcome to SmartPrint API",
        "docs": "/api/docs",
        "health": "/api/health",
        "database": "MySQL (PyMySQL)",
    }
