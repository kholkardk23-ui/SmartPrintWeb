from logging.config import fileConfig
import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

# ============================================================
# ALEMBIC CONFIGURATION
# ============================================================

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add backend directory to Python path
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from app.config import settings
from app.database import Base
import app.models  # Ensure all models are registered


# ============================================================
# DATABASE URL AND SSL CONFIGURATION
# ============================================================

database_url = make_url(settings.DATABASE_URL)

# Remove Aiven's ssl-mode query parameter.
# PyMySQL does not accept "ssl-mode" as a connection argument.
query_params = dict(database_url.query)

ssl_mode = query_params.pop("ssl-mode", None)

if ssl_mode is None:
    ssl_mode = query_params.pop("ssl_mode", None)
else:
    query_params.pop("ssl_mode", None)

database_url = database_url.set(query=query_params)

# Keep SSL enabled for Aiven MySQL.
connect_args = {}

if ssl_mode and str(ssl_mode).upper() in ("REQUIRED", "VERIFY_CA", "VERIFY_IDENTITY"):
    connect_args["ssl"] = {"check_hostname": True}

# Escape percent signs for Alembic ConfigParser.
config.set_main_option(
    "sqlalchemy.url",
    database_url.render_as_string(hide_password=False).replace("%", "%%"),
)

# Pass SSL settings to the SQLAlchemy engine.
config.attributes["connect_args"] = connect_args

target_metadata = Base.metadata


# ============================================================
# OFFLINE MIGRATIONS
# ============================================================

def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""

    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ============================================================
# ONLINE MIGRATIONS
# ============================================================

def run_migrations_online() -> None:
    """Run migrations using a live database connection."""

    connect_args = config.attributes.get("connect_args", {})

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


# ============================================================
# RUN MIGRATIONS
# ============================================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()