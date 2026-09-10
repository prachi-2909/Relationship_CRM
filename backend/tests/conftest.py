"""Test fixtures.

Runs on a throwaway file-backed SQLite database (real per-connection isolation,
unlike shared in-memory) unless TEST_DATABASE_URL points elsewhere.
"""

import os

os.environ.setdefault("ENABLE_SCHEDULER", "false")
# Tests must be deterministic and offline: force the LLM stub even when a real
# endpoint is configured in .env (env vars outrank the .env file in pydantic).
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_MODEL"] = "stub"

import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app
from app.models import Base
from app.models.official import Official
from app.models.user import Role, User, UserStatus
from app.scripts.seed_unit_types import ensure_defaults
from app.security.passwords import hash_password

_tmp_dir = tempfile.mkdtemp(prefix="rcrm_test_")
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL", f"sqlite+pysqlite:///{Path(_tmp_dir) / 'test.db'}"
)

_is_sqlite = TEST_DB_URL.startswith("sqlite")
engine = create_engine(
    TEST_DB_URL,
    future=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)
TestSession = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


@pytest.fixture(autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seeder = TestSession()
    try:
        ensure_defaults(seeder)
        seeder.commit()
    finally:
        seeder.close()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    """Session for test-side setup and assertions."""
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    """TestClient whose requests each get their own session on the shared engine."""

    def _override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db):
    def _make(
        email: str = "user@example.com",
        password: str = "password123",
        role: Role = Role.RELATIONSHIP_MANAGER,
        name: str = "Test User",
        status: UserStatus = UserStatus.ACTIVE,
    ) -> User:
        user = User(
            name=name,
            email=email.lower(),
            password_hash=hash_password(password),
            role=role,
            status=status,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def make_official(db):
    def _make(name: str = "Test Official", level: str | None = None) -> Official:
        official = Official(name=name, level=level)
        db.add(official)
        db.commit()
        db.refresh(official)
        return official

    return _make


@pytest.fixture
def login(client):
    def _login(email: str, password: str):
        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.text
        return response

    return _login
