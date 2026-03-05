from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

import app.database as database
from app.config import settings
from app.models import Attachment


def _snapshot_db(destination: Path) -> None:
    src = sqlite3.connect(str(settings.db_path))
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _build_manifest(db: Session) -> dict:
    rows = db.query(Attachment).all()
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "attachments": [
            {
                "id": row.id,
                "paper_id": row.paper_id,
                "original_filename": row.original_filename,
                "stored_path": row.stored_path,
                "sha256": row.sha256,
                "file_size": row.file_size,
            }
            for row in rows
        ],
    }


def run_backup(db: Session, kind: str = "daily") -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{kind}_{timestamp}.zip"
    archive_path = settings.backups_dir / filename

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_snapshot = tmp_path / "app.db"
        _snapshot_db(db_snapshot)

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(_build_manifest(db), ensure_ascii=True, indent=2), encoding="utf-8")

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_snapshot, arcname="app.db")
            zf.write(manifest_path, arcname="manifest.json")

            if kind == "weekly":
                for file in settings.attachments_dir.rglob("*"):
                    if file.is_file():
                        arcname = str(Path("attachments") / file.relative_to(settings.attachments_dir))
                        zf.write(file, arcname=arcname)

    return filename


def list_backups() -> list[dict]:
    items = []
    for file in settings.backups_dir.glob("backup_*.zip"):
        stat = file.stat()
        items.append(
            {
                "filename": file.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime),
            }
        )

    return sorted(items, key=lambda x: x["created_at"], reverse=True)


def restore_backup(filename: str) -> None:
    archive_path = settings.backups_dir / filename
    if not archive_path.exists():
        raise FileNotFoundError(f"backup not found: {filename}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(tmp_path)

        db_snapshot = tmp_path / "app.db"
        if not db_snapshot.exists():
            raise ValueError("backup archive missing app.db")

        database.engine.dispose()
        shutil.copy2(db_snapshot, settings.db_path)

        extracted_attachments = tmp_path / "attachments"
        if extracted_attachments.exists():
            shutil.rmtree(settings.attachments_dir, ignore_errors=True)
            settings.attachments_dir.mkdir(parents=True, exist_ok=True)
            for file in extracted_attachments.rglob("*"):
                if file.is_file():
                    target = settings.attachments_dir / file.relative_to(extracted_attachments)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, target)
