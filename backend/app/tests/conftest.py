from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.database as database
from app.config import settings
from app.main import app
from app.models import Base


@pytest.fixture()
def temp_env(tmp_path: Path):
    original = {
        "storage_dir": settings.storage_dir,
        "attachments_dir": settings.attachments_dir,
        "backups_dir": settings.backups_dir,
        "db_path": settings.db_path,
    }

    storage = tmp_path / "storage"
    attachments = storage / "attachments"
    backups = storage / "backups"
    db_path = storage / "app.db"

    attachments.mkdir(parents=True, exist_ok=True)
    backups.mkdir(parents=True, exist_ok=True)

    object.__setattr__(settings, "storage_dir", storage)
    object.__setattr__(settings, "attachments_dir", attachments)
    object.__setattr__(settings, "backups_dir", backups)
    object.__setattr__(settings, "db_path", db_path)

    database.reset_engine(db_path)
    Base.metadata.create_all(bind=database.engine)

    yield

    database.reset_engine(original["db_path"])
    object.__setattr__(settings, "storage_dir", original["storage_dir"])
    object.__setattr__(settings, "attachments_dir", original["attachments_dir"])
    object.__setattr__(settings, "backups_dir", original["backups_dir"])
    object.__setattr__(settings, "db_path", original["db_path"])


@pytest.fixture()
def db_session(temp_env):
    db = database.SessionLocal()
    try:
        yield db
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def client(temp_env, monkeypatch):
    monkeypatch.setattr("app.main.start_scheduler", lambda: None)
    monkeypatch.setattr("app.main.stop_scheduler", lambda: None)
    with TestClient(app) as test_client:
        yield test_client
