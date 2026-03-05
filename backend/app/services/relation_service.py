from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import Paper, PaperRelation, PaperStatus


@dataclass
class RelationCandidate:
    paper_id: str
    title: str | None
    year: int | None
    snippet: str | None
    score: float


WORD_RE = re.compile(r"[A-Za-z0-9]+")


def canonicalize_relation(source_paper_id: str, target_paper_id: str, relation_type: str) -> tuple[str, str]:
    if relation_type != "related":
        return source_paper_id, target_paper_id
    if source_paper_id <= target_paper_id:
        return source_paper_id, target_paper_id
    return target_paper_id, source_paper_id


def normalize_note(note: str | None, max_len: int = 500) -> str | None:
    if note is None:
        return None
    cleaned = re.sub(r"\s+", " ", note).strip()
    if not cleaned:
        return None
    if len(cleaned) > max_len:
        return cleaned[:max_len]
    return cleaned


def _compact_text(value: str | None, max_len: int) -> str:
    if not value:
        return ""
    normalized = " ".join(value.split())
    if len(normalized) <= max_len:
        return normalized
    return normalized[:max_len]


def _paper_text_for_similarity(paper: Paper) -> str:
    title = _compact_text(paper.title, 600)
    abstract = _compact_text(paper.abstract, 2400)
    return f"{title} {abstract}".strip()


def _similarity_score(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    return max(
        float(fuzz.token_set_ratio(left, right)),
        float(fuzz.partial_ratio(left, right)),
    )


def _weighted_pair_score(
    source_title: str,
    source_abstract: str,
    candidate_title: str,
    candidate_abstract: str,
) -> float:
    # Common field-weighted relevance: title dominates, abstract assists.
    weighted_total = 0.0
    weight_sum = 0.0

    if source_title and candidate_title:
        weighted_total += _similarity_score(source_title, candidate_title) * 0.65
        weight_sum += 0.65

    if source_abstract and candidate_abstract:
        weighted_total += _similarity_score(source_abstract, candidate_abstract) * 0.25
        weight_sum += 0.25

    source_full = f"{source_title} {source_abstract}".strip()
    candidate_full = f"{candidate_title} {candidate_abstract}".strip()
    if source_full and candidate_full:
        weighted_total += _similarity_score(source_full, candidate_full) * 0.10
        weight_sum += 0.10

    if weight_sum <= 0:
        return 0.0
    return weighted_total / weight_sum


def _weighted_query_score(query: str, title: str, abstract: str) -> float:
    title_score = _similarity_score(query, title)
    abstract_score = _similarity_score(query, abstract)

    if query in title:
        title_score = max(title_score, 100.0)
    if query in abstract:
        abstract_score = max(abstract_score, 100.0)

    weighted_total = 0.0
    weight_sum = 0.0

    if title:
        weighted_total += title_score * 0.7
        weight_sum += 0.7
    if abstract:
        weighted_total += abstract_score * 0.3
        weight_sum += 0.3

    if weight_sum <= 0:
        return 0.0
    return weighted_total / weight_sum


def _build_snippet(text_value: str | None, query: str | None) -> str | None:
    if not text_value:
        return None
    content = " ".join(text_value.split())
    if not content:
        return None
    if not query:
        return f"{content[:220].rstrip()}..." if len(content) > 220 else content

    query_lc = query.lower()
    content_lc = content.lower()
    pos = content_lc.find(query_lc)
    if pos < 0:
        return f"{content[:220].rstrip()}..." if len(content) > 220 else content

    left = max(0, pos - 90)
    right = min(len(content), pos + len(query) + 120)
    prefix = "..." if left > 0 else ""
    suffix = "..." if right < len(content) else ""
    return f"{prefix}{content[left:right].strip()}{suffix}"


def _fuzzy_threshold(query: str) -> float:
    compact_len = len(re.sub(r"\s+", "", query))
    if compact_len <= 3:
        return 92.0
    if compact_len <= 6:
        return 84.0
    return 76.0


def get_existing_relation_types(
    db: Session,
    source_paper_id: str,
    candidate_ids: list[str],
) -> dict[str, list[str]]:
    if not candidate_ids:
        return {}

    result_map: dict[str, set[str]] = {paper_id: set() for paper_id in candidate_ids}

    cite_rows = db.execute(
        select(PaperRelation).where(
            and_(
                PaperRelation.source_paper_id == source_paper_id,
                PaperRelation.target_paper_id.in_(candidate_ids),
                PaperRelation.relation_type == "cite",
            )
        )
    ).scalars().all()
    for row in cite_rows:
        result_map.setdefault(row.target_paper_id, set()).add("cite")

    related_rows = db.execute(
        select(PaperRelation).where(
            and_(
                PaperRelation.relation_type == "related",
                or_(
                    and_(
                        PaperRelation.source_paper_id == source_paper_id,
                        PaperRelation.target_paper_id.in_(candidate_ids),
                    ),
                    and_(
                        PaperRelation.target_paper_id == source_paper_id,
                        PaperRelation.source_paper_id.in_(candidate_ids),
                    ),
                ),
            )
        )
    ).scalars().all()
    for row in related_rows:
        peer_id = row.target_paper_id if row.source_paper_id == source_paper_id else row.source_paper_id
        result_map.setdefault(peer_id, set()).add("related")

    return {paper_id: sorted(list(types)) for paper_id, types in result_map.items() if types}


def _candidate_rows(db: Session, source_paper_id: str) -> list[Paper]:
    return db.execute(
        select(Paper).where(
            and_(
                Paper.status == PaperStatus.CONFIRMED.value,
                Paper.id != source_paper_id,
            )
        )
    ).scalars().all()


def suggest_relation_candidates(
    db: Session,
    source_paper: Paper,
    query: str | None,
    limit: int = 10,
) -> list[RelationCandidate]:
    papers = _candidate_rows(db, source_paper.id)
    if not papers:
        return []

    q = " ".join((query or "").split()).strip() or None
    source_title = _compact_text(source_paper.title, 600).lower()
    source_abstract = _compact_text(source_paper.abstract, 2400).lower()
    threshold = _fuzzy_threshold(q) if q else None
    candidates: list[RelationCandidate] = []

    for paper in papers:
        candidate_title = _compact_text(paper.title, 600).lower()
        candidate_abstract = _compact_text(paper.abstract, 2400).lower()
        candidate_text = f"{candidate_title} {candidate_abstract}".strip()
        if not candidate_text:
            continue

        if q:
            q_lc = q.lower()
            score = _weighted_query_score(q_lc, candidate_title, candidate_abstract)
            if threshold is not None and score < threshold:
                continue
            snippet = _build_snippet(paper.abstract or paper.title, q)
        else:
            score = _weighted_pair_score(
                source_title=source_title,
                source_abstract=source_abstract,
                candidate_title=candidate_title,
                candidate_abstract=candidate_abstract,
            )
            snippet = _build_snippet(paper.abstract or paper.title, None)

        candidates.append(
            RelationCandidate(
                paper_id=paper.id,
                title=paper.title,
                year=paper.year,
                snippet=snippet,
                score=round(score, 2),
            )
        )

    candidates.sort(
        key=lambda item: (
            float(item.score),
            item.year or -1,
        ),
        reverse=True,
    )
    return candidates[:limit]
