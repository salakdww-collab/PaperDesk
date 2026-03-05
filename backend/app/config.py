from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    frontend_dist_dir: Path
    storage_dir: Path
    attachments_dir: Path
    backups_dir: Path
    db_path: Path
    api_host: str
    api_port: int



def load_settings() -> Settings:
    project_root = Path(os.getenv("APP_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
    frontend_dist_dir = Path(
        os.getenv("APP_FRONTEND_DIST_DIR", str(project_root / "frontend" / "dist"))
    ).resolve()
    storage_dir = Path(os.getenv("APP_STORAGE_DIR", str(project_root / "storage"))).resolve()
    attachments_dir = Path(os.getenv("APP_ATTACHMENTS_DIR", str(storage_dir / "attachments"))).resolve()
    backups_dir = Path(os.getenv("APP_BACKUPS_DIR", str(storage_dir / "backups"))).resolve()
    db_path = Path(os.getenv("APP_DB_PATH", str(storage_dir / "app.db"))).resolve()

    attachments_dir.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    api_host = os.getenv("APP_HOST", "0.0.0.0")
    api_port = int(os.getenv("APP_PORT", "8000"))

    return Settings(
        project_root=project_root,
        frontend_dist_dir=frontend_dist_dir,
        storage_dir=storage_dir,
        attachments_dir=attachments_dir,
        backups_dir=backups_dir,
        db_path=db_path,
        api_host=api_host,
        api_port=api_port,
    )


settings = load_settings()
