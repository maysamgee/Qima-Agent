from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.database import Base, get_engine, session_factory
from app.scoring import seed_policies


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("QUEUE_PROVIDER", "local")
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "documents"))
    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = get_engine()
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
    with session_factory()() as db:
        seed_policies(db)
        db.commit()
    yield
    engine.dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def db():
    with session_factory()() as session:
        yield session


@pytest.fixture
def client():
    from app.main import app, limits

    limits.clear()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def candidate_id(client):
    from app.workflow.discovery import process_job

    response = client.post(
        "/api/jobs",
        json={"agent_type": "SOURCING", "query": "Find producers in Ethiopia", "country": "Ethiopia"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    assert process_job(response.json()["id"])
    return client.get(f"/api/jobs/{response.json()['id']}").json()["candidates"][0]["id"]


def post(client, path, body=None, key=None):
    return client.post(path, json=body or {}, headers={"Idempotency-Key": key or str(uuid4())})
