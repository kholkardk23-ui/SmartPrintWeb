import io
import os
import pytest
import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
test_connect_args = {}
test_poolclass = None

if TEST_DB_URL.startswith("sqlite"):
    test_connect_args = {"check_same_thread": False}
    test_poolclass = StaticPool

test_engine = create_engine(
    TEST_DB_URL,
    connect_args=test_connect_args,
    poolclass=test_poolclass,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
