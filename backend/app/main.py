import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.config import settings
from app.database import engine, Base, verify_database_connection, DatabaseConnectionError
from app.routes import health, files, orders, payments, printers, sessions

logger = logging.getLogger("smartprint.main")
logging.basicConfig(level=logging.INFO)


def run_auto_migrations():
    """Run Alembic migrations programmatically to bring the database to the head revision."""
    try:
        from alembic.config import Config
        from alembic import command

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ini_path = os.path.join(base_dir, "alembic.ini")
        if os.path.exists(ini_path):
            alembic_cfg = Config(ini_path)
            alembic_cfg.set_main_option(
                "script_location",
                os.path.join(base_dir, "alembic"),
            )
            command.upgrade(alembic_cfg, "head")
            logger.info("Alembic migrations upgraded to head successfully.")
        else:
            logger.warning("alembic.ini not found at %s", ini_path)
    except Exception as exc:
        logger.warning("Alembic programmatic migration notice: %s", exc)


def ensure_schema_integrity():
    """Verify that critical columns exist in the database and add any missing ones defensively."""
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        if "orders" not in existing_tables:
            return

        columns = {c["name"] for c in inspector.get_columns("orders")}
        with engine.begin() as conn:
            if "payment_status" not in columns:
                logger.info("Adding missing column 'payment_status' to orders table...")
                conn.execute(
                    text("ALTER TABLE orders ADD COLUMN payment_status VARCHAR(50) DEFAULT 'PENDING'")
                )
            if "payment_reference" not in columns:
                logger.info("Adding missing column 'payment_reference' to orders table...")
                conn.execute(
                    text("ALTER TABLE orders ADD COLUMN payment_reference VARCHAR(100) NULL")
                )
            if "payment_timestamp" not in columns:
                logger.info("Adding missing column 'payment_timestamp' to orders table...")
                conn.execute(
                    text("ALTER TABLE orders ADD COLUMN payment_timestamp DATETIME NULL")
                )
            if "payment_session_id" not in columns:
                logger.info("Adding missing column 'payment_session_id' to orders table...")
                conn.execute(
                    text("ALTER TABLE orders ADD COLUMN payment_session_id VARCHAR(100) NULL")
                )
            if "is_paid" not in columns:
                logger.info("Adding missing column 'is_paid' to orders table...")
                conn.execute(
                    text("ALTER TABLE orders ADD COLUMN is_paid TINYINT(1) NOT NULL DEFAULT 0")
                )
        logger.info("Schema integrity verified for orders table.")
    except Exception as exc:
        logger.warning("Schema integrity check notice: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: verify MySQL database connectivity, run migrations, and ensure table schemas."""
    logger.info("Initializing SmartPrint backend...")
    try:
        verify_database_connection()
        run_auto_migrations()
        Base.metadata.create_all(bind=engine)
        ensure_schema_integrity()
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
cors_origins = (
    settings.CORS_ORIGINS
    if isinstance(settings.CORS_ORIGINS, list)
    else [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
)
for default_origin in [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "https://smart-print-web-gules.vercel.app",
]:
    if default_origin not in cors_origins:
        cors_origins.append(default_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"^https://[a-zA-Z0-9-]+\.vercel\.app$",
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
