import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

logger = logging.getLogger("smartprint.database")

database_url = settings.DATABASE_URL
connect_args = {}

try:
    parsed_url = make_url(database_url)

    if parsed_url.drivername.startswith("mysql"):
        # Remove URL query parameters that PyMySQL may misinterpret.
        query = dict(parsed_url.query)
        ssl_mode = query.pop("ssl-mode", None)
        query.pop("ssl_mode", None)

        parsed_url = parsed_url.set(query=query)

        # Aiven MySQL requires an encrypted connection.
        if ssl_mode and ssl_mode.upper() == "REQUIRED":
            connect_args["ssl"] = {"check_hostname": True}

        connect_args["connect_timeout"] = 10

        database_url = parsed_url

    elif parsed_url.drivername.startswith("sqlite"):
        connect_args["check_same_thread"] = False

except Exception:
    logger.exception("Failed to parse database configuration.")
    raise

engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


class DatabaseConnectionError(Exception):
    """Raised when the database connection fails."""
    pass


def verify_database_connection():
    """Verify database connectivity without exposing credentials."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        logger.info("Database connection verified successfully.")

    except Exception as exc:
        error_msg = (
            "Unable to connect to the configured database. "
            f"Error type: {type(exc).__name__}. "
            "Verify the database credentials, network access, and SSL settings."
        )
        logger.error(error_msg)
        raise DatabaseConnectionError(error_msg) from exc


def check_database_health() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("Database health check failed.")
        return False


def get_db():
    """Provide a database session to FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()