import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from app.config import settings

logger = logging.getLogger("smartprint.database")

# Configure connection arguments
connect_args = {}
if "mysql" in settings.DATABASE_URL:
    connect_args["connect_timeout"] = 3
elif "sqlite" in settings.DATABASE_URL:
    connect_args["check_same_thread"] = False

# Build MySQL engine with connection health pre-ping and connection recycle
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class DatabaseConnectionError(Exception):
    """Exception raised when MySQL database connection fails."""
    pass


def verify_database_connection():
    """
    Verify MySQL connectivity on application startup.
    Raises DatabaseConnectionError with sanitized message if connection fails.
    Never exposes passwords or sensitive credentials.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        safe_url = settings.sanitized_database_url
        error_msg = (
            f"Unable to connect to MySQL database at '{safe_url}'. "
            f"Please verify MySQL server is running and credentials/database exist. "
            f"Error details: {type(exc).__name__}: {str(exc).split('@')[-1] if '@' in str(exc) else str(exc)}"
        )
        logger.error(error_msg)
        raise DatabaseConnectionError(error_msg) from exc


def check_database_health() -> bool:
    """
    Non-blocking health probe for database connectivity.
    Returns True if database can execute a ping query, False otherwise.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_db():
    """FastAPI dependency for providing database sessions per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
