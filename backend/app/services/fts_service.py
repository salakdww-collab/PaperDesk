from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Attachment, Note, Paper, PaperAuthor


def rebuild_paper_fts(db: Session, paper_id: str) -> None:
    paper = db.get(Paper, paper_id)
    if not paper:
        return

    author_rows = db.execute(
        select(PaperAuthor).where(PaperAuthor.paper_id == paper_id).order_by(PaperAuthor.author_order)
    ).scalars()
    authors = [row.author.name for row in author_rows if row.author]

    notes = db.execute(select(Note).where(Note.paper_id == paper_id)).scalars().all()
    notes_text = "\n".join(filter(None, [(n.quote_text or "") + "\n" + n.note_text for n in notes]))

    attachments = db.execute(select(Attachment).where(Attachment.paper_id == paper_id)).scalars().all()
    content_text = "\n".join([a.extracted_text or "" for a in attachments])

    db.execute(text("DELETE FROM paper_fts WHERE paper_id = :paper_id"), {"paper_id": paper_id})
    db.execute(
        text(
            """
            INSERT INTO paper_fts (paper_id, title, authors_text, abstract, notes_text, content_text)
            VALUES (:paper_id, :title, :authors_text, :abstract, :notes_text, :content_text)
            """
        ),
        {
            "paper_id": paper_id,
            "title": paper.title or "",
            "authors_text": ", ".join(authors),
            "abstract": paper.abstract or "",
            "notes_text": notes_text,
            "content_text": content_text,
        },
    )


def clear_paper_fts(db: Session, paper_id: str) -> None:
    db.execute(text("DELETE FROM paper_fts WHERE paper_id = :paper_id"), {"paper_id": paper_id})
