import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

os.environ["DEBUG"] = "false"
os.environ["DATABASE_AUTO_CREATE_TABLES"] = "false"

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


def _test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")


def _guard_test_database_url(database_url: str) -> None:
    url = make_url(database_url)
    if url.drivername.startswith("sqlite"):
        return

    database_name = url.database or ""
    if "test" not in database_name.lower():
        raise RuntimeError(
            "Refusing to run tests against a non-test database. "
            "Set TEST_DATABASE_URL to a disposable database whose name contains 'test'."
        )

    if database_name == "purchasing_ai":
        raise RuntimeError("Refusing to run tests against the development database.")


TEST_DATABASE_URL = _test_database_url()
_guard_test_database_url(TEST_DATABASE_URL)

engine_kwargs = {}
if TEST_DATABASE_URL.startswith("sqlite"):
    engine_kwargs = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }

test_engine = create_engine(TEST_DATABASE_URL, **engine_kwargs)


@event.listens_for(test_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if TEST_DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def reset_test_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def session_factory():
    return TestingSessionLocal


@pytest.fixture
def client(session_factory) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
