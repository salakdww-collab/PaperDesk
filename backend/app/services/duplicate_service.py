from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import DuplicateResolution, Paper, PaperAuthor


@dataclass
class DuplicateMatch:
    paper_id: str
    title: str | None
    score: float



def _author_text(paper: Paper) -> str:
    sorted_authors = sorted(paper.authors, key=lambda x: x.author_order)
    return ", ".join([row.author.name for row in sorted_authors if row.author])


def _combined_text(paper: Paper) -> str:
    title = paper.title or ""
    return f"{title} | {_author_text(paper)}".strip()


def find_duplicates(db: Session, source_paper_id: str, threshold: float = 75.0) -> list[DuplicateMatch]:
    source = db.get(Paper, source_paper_id)
    if not source:
        return []

    papers = db.execute(
        select(Paper)
        .where(and_(Paper.id != source_paper_id, Paper.status == "confirmed"))
    ).scalars().all()

    ignored_pairs = {
        (r.paper_id, r.duplicate_paper_id)
        for r in db.execute(select(DuplicateResolution).where(DuplicateResolution.status == "ignored")).scalars().all()
    }

    source_text = _combined_text(source)
    matches: list[DuplicateMatch] = []
    for paper in papers:
        if (source_paper_id, paper.id) in ignored_pairs:
            continue

        candidate_text = _combined_text(paper)
        score = fuzz.token_set_ratio(source_text, candidate_text)
        if score >= threshold:
            matches.append(DuplicateMatch(paper_id=paper.id, title=paper.title, score=round(float(score), 2)))

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches
