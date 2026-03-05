from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

def _build_engine(db_path: Path) -> Engine:
    database_url = f"sqlite:///{db_path}"
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        future=True,
    )


engine = _build_engine(settings.db_path)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table_name});")).mappings().all()
    return any(row["name"] == column_name for row in rows)


def reset_engine(db_path: Path | None = None) -> None:
    global engine, SessionLocal
    engine.dispose()
    engine = _build_engine(db_path or settings.db_path)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def init_db(base_metadata) -> None:
    base_metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        conn.execute(text("PRAGMA synchronous=NORMAL;"))
        if not _column_exists(conn, "papers", "summary_label"):
            conn.execute(
                text(
                    "ALTER TABLE papers ADD COLUMN summary_label VARCHAR(64) NOT NULL DEFAULT 'Abstract';"
                )
            )
        if not _column_exists(conn, "papers", "summary"):
            conn.execute(
                text(
                    "ALTER TABLE papers ADD COLUMN summary TEXT;"
                )
            )
        if not _column_exists(conn, "papers", "original_title"):
            conn.execute(
                text(
                    "ALTER TABLE papers ADD COLUMN original_title VARCHAR(1000);"
                )
            )
        conn.execute(
            text(
                "UPDATE papers SET original_title = title WHERE (original_title IS NULL OR TRIM(original_title) = '') AND title IS NOT NULL;"
            )
        )
        conn.execute(
            text(
                "UPDATE papers SET summary = abstract WHERE (summary IS NULL OR TRIM(summary) = '') AND abstract IS NOT NULL;"
            )
        )
        conn.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS paper_fts USING fts5(
                    paper_id UNINDEXED,
                    title,
                    authors_text,
                    abstract,
                    notes_text,
                    content_text
                );
                """
            )
        )
        conn.commit()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
