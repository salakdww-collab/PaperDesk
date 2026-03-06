from __future__ import annotations

import hashlib
import mimetypes
import re
import subprocess
import webbrowser
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from rapidfuzz import fuzz
from sqlalchemy import and_, delete as sql_delete, func, or_, select, text
from sqlalchemy.orm import Session, joinedload, selectinload

from app.config import settings
from app.database import get_db
from app.models import (
    Attachment,
    Author,
    DuplicateResolution,
    Note,
    Paper,
    PaperAuthor,
    PaperLink,
    PaperRelation,
    PaperStatus,
    PaperTag,
    Tag,
)
from app.schemas import (
    AttachmentOut,
    AuthorOut,
    BackupItem,
    BackupRestoreRequest,
    BackupRunRequest,
    CitationBatchRequest,
    CitationBatchResponse,
    CitationResponse,
    ConfirmPaperRequest,
    CreatePaperRelationRequest,
    CreatePaperLinkRequest,
    CreateNoteRequest,
    CreateReviewRequest,
    DuplicateCandidate,
    DuplicateResolveRequest,
    ImportPdfResponse,
    NoteOut,
    PaperRelationItemOut,
    PaperRelationsResponse,
    RelationCandidateOut,
    PaperListResponse,
    PaperLinkOut,
    PaperOut,
    ReviewOut,
    SearchResponse,
    SearchResultOut,
    TagOut,
    UpdateNoteRequest,
    UpdatePaperRequest,
    UpdateReviewRequest,
)
from app.services.backup_service import list_backups, restore_backup, run_backup
from app.services.citation_service import render_citation
from app.services.duplicate_service import find_duplicates
from app.services.fts_service import clear_paper_fts, rebuild_paper_fts
from app.services.metadata_service import extract_metadata_candidate, normalize_author_name
from app.services.pdf_service import parse_pdf
from app.services.relation_service import (
    canonicalize_relation,
    get_existing_relation_types,
    normalize_note,
    suggest_relation_candidates,
)

router = APIRouter(prefix="/api/v1", tags=["api"])
WORD_RE = re.compile(r"[A-Za-z0-9]+")
DEFAULT_SUMMARY_LABEL = "Abstract"
MAX_BIBTEX_OVERRIDE_LEN = 20000


def _paper_link_to_out(link: PaperLink) -> PaperLinkOut:
    return PaperLinkOut(
        id=link.id,
        paper_id=link.paper_id,
        label=link.label,
        url=link.url,
        created_at=link.created_at,
    )


def _get_paper_or_404(paper_id: str, db: Session) -> Paper:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="paper not found")
    return paper


def _ensure_confirmed_paper(paper_id: str, db: Session) -> Paper:
    paper = _get_paper_or_404(paper_id, db)
    if paper.status != PaperStatus.CONFIRMED.value:
        raise HTTPException(status_code=400, detail="paper must be confirmed")
    return paper


def _relation_item_out(
    relation: PaperRelation,
    current_paper_id: str,
    peer_title: str | None,
    peer_year: int | None,
    read_only: bool,
) -> PaperRelationItemOut:
    peer_paper_id = relation.target_paper_id if relation.source_paper_id == current_paper_id else relation.source_paper_id
    return PaperRelationItemOut(
        relation_id=relation.id,
        peer_paper_id=peer_paper_id,
        peer_title=peer_title,
        peer_year=peer_year,
        note=relation.note,
        updated_at=relation.updated_at,
        relation_type=relation.relation_type,
        read_only=read_only,
    )


def _query_to_acronym(query: str) -> str | None:
    if " " in query:
        return None
    compact = re.sub(r"[^A-Za-z0-9]", "", query).upper()
    if 2 <= len(compact) <= 10:
        return compact
    return None


def _find_acronym_span(text_value: str | None, acronym: str) -> tuple[int, int] | None:
    if not text_value:
        return None

    words = list(WORD_RE.finditer(text_value))
    target_len = len(acronym)
    if target_len < 2 or len(words) < target_len:
        return None

    initials = [item.group(0)[0].upper() for item in words]
    for index in range(0, len(initials) - target_len + 1):
        if "".join(initials[index:index + target_len]) == acronym:
            return words[index].start(), words[index + target_len - 1].end()
    return None


def _build_search_snippet(text_value: str | None, query: str, acronym: str | None) -> str | None:
    if not text_value:
        return None

    content = " ".join(text_value.split())
    if not content:
        return None

    query_lc = query.lower()
    content_lc = content.lower()
    exact_index = content_lc.find(query_lc)

    if exact_index >= 0:
        span_start = exact_index
        span_end = exact_index + len(query)
    else:
        acronym_span = _find_acronym_span(content, acronym) if acronym else None
        if acronym_span:
            span_start, span_end = acronym_span
        else:
            if len(content) <= 220:
                return content
            return f"{content[:220].rstrip()}..."

    left = max(0, span_start - 90)
    right = min(len(content), span_end + 120)
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


def _normalize_summary_label(value: str | None) -> str:
    if value is None:
        return DEFAULT_SUMMARY_LABEL
    normalized = " ".join(value.split()).strip()
    if not normalized:
        return DEFAULT_SUMMARY_LABEL
    return normalized[:64]


def _normalize_summary_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_bibtex_override(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized[:MAX_BIBTEX_OVERRIDE_LEN]


def _is_scholar_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.lower()
    return normalized == "scholar.google.com" or normalized.startswith("scholar.google.")


def _normalize_scholar_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None

    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=400, detail="scholar_url must be a valid https URL")
    if not _is_scholar_host(parsed.hostname):
        raise HTTPException(status_code=400, detail="scholar_url must use scholar.google.*")
    return normalized



def _paper_to_out(paper: Paper) -> PaperOut:
    author_rows = sorted(paper.authors, key=lambda x: x.author_order)
    links = sorted(paper.links, key=lambda x: x.created_at, reverse=True)
    attachments = sorted(paper.attachments, key=lambda x: x.imported_at)
    return PaperOut(
        id=paper.id,
        status=paper.status,
        title=paper.title,
        original_title=paper.original_title,
        year=paper.year,
        venue=paper.venue,
        doi=paper.doi,
        arxiv_id=paper.arxiv_id,
        abstract=paper.abstract,
        summary=paper.summary,
        bibtex_override=paper.bibtex_override,
        scholar_url=paper.scholar_url,
        summary_label=_normalize_summary_label(paper.summary_label),
        language=paper.language,
        needs_manual_metadata=paper.needs_manual_metadata,
        created_at=paper.created_at,
        updated_at=paper.updated_at,
        authors=[AuthorOut(id=row.author.id, name=row.author.name) for row in author_rows if row.author],
        attachments=[
            AttachmentOut(
                id=item.id,
                original_filename=item.original_filename,
                page_count=item.page_count,
                file_size=item.file_size,
                imported_at=item.imported_at,
            )
            for item in attachments
        ],
        tags=[TagOut(id=row.tag.id, name=row.tag.name, color=row.tag.color) for row in paper.tags if row.tag],
        links=[_paper_link_to_out(item) for item in links],
    )



def _note_to_out(note: Note) -> NoteOut:
    return NoteOut(
        id=note.id,
        paper_id=note.paper_id,
        attachment_id=note.attachment_id,
        page_number=note.page_number,
        quote_text=note.quote_text,
        note_text=note.note_text,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _note_out_to_review_out(note_out: NoteOut) -> ReviewOut:
    return ReviewOut(**note_out.model_dump())


def _create_note_core(paper_id: str, payload: CreateNoteRequest, db: Session) -> NoteOut:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="paper not found")

    note = Note(
        paper_id=paper_id,
        attachment_id=payload.attachment_id,
        page_number=payload.page_number,
        quote_text=payload.quote_text,
        note_text=payload.note_text,
    )
    db.add(note)
    db.flush()
    rebuild_paper_fts(db, paper_id)
    db.commit()
    db.refresh(note)
    return _note_to_out(note)


def _list_notes_core(paper_id: str, db: Session) -> list[NoteOut]:
    rows = (
        db.execute(select(Note).where(Note.paper_id == paper_id).order_by(Note.created_at.desc()))
        .scalars()
        .all()
    )
    return [_note_to_out(row) for row in rows]


def _delete_note_core(note_id: str, db: Session, not_found_detail: str = "note not found") -> None:
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=not_found_detail)

    paper_id = note.paper_id
    db.delete(note)
    db.flush()
    rebuild_paper_fts(db, paper_id)
    db.commit()


def _update_note_core(
    note_id: str,
    payload: UpdateNoteRequest,
    db: Session,
    not_found_detail: str = "note not found",
) -> NoteOut:
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=not_found_detail)

    text = payload.note_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="note_text cannot be empty")

    note.note_text = text
    note.quote_text = payload.quote_text
    note.page_number = payload.page_number
    note.attachment_id = payload.attachment_id

    paper_id = note.paper_id
    db.flush()
    rebuild_paper_fts(db, paper_id)
    db.commit()
    db.refresh(note)
    return _note_to_out(note)


def _apply_authors(db: Session, paper: Paper, authors: list[str]) -> None:
    paper.authors.clear()
    for idx, raw_name in enumerate(authors):
        name = raw_name.strip()
        if not name:
            continue
        normalized = normalize_author_name(name)
        author = db.execute(select(Author).where(Author.normalized_name == normalized)).scalar_one_or_none()
        if not author:
            author = Author(name=name, normalized_name=normalized)
            db.add(author)
            db.flush()
        paper.authors.append(PaperAuthor(author_id=author.id, author_order=idx))



def _apply_tags(db: Session, paper: Paper, tags: list[str]) -> None:
    normalized_tags: list[str] = []
    seen_names: set[str] = set()
    for raw_name in tags:
        name = raw_name.strip()
        if not name:
            continue
        if name in seen_names:
            continue
        seen_names.add(name)
        normalized_tags.append(name)

    desired_tag_set = set(normalized_tags)
    current_rows = list(paper.tags)
    current_tag_names = {row.tag.name for row in current_rows if row.tag}

    for row in current_rows:
        if not row.tag or row.tag.name not in desired_tag_set:
            paper.tags.remove(row)

    for name in normalized_tags:
        if name in current_tag_names:
            continue
        tag = db.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()
        if not tag:
            tag = Tag(name=name, color=None)
            db.add(tag)
            db.flush()
        paper.tags.append(PaperTag(tag_id=tag.id))


def _cleanup_orphan_tags(db: Session) -> None:
    orphan_tag_ids = db.execute(
        select(Tag.id)
        .outerjoin(PaperTag, PaperTag.tag_id == Tag.id)
        .group_by(Tag.id)
        .having(func.count(PaperTag.id) == 0)
    ).scalars().all()
    if not orphan_tag_ids:
        return
    db.execute(sql_delete(Tag).where(Tag.id.in_(orphan_tag_ids)))


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/import/pdf", response_model=ImportPdfResponse)
async def import_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)) -> ImportPdfResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    file_ext = Path(file.filename).suffix.lower()
    if file_ext != ".pdf":
        raise HTTPException(status_code=400, detail="only pdf files are supported")

    paper = Paper(status=PaperStatus.DRAFT.value)
    db.add(paper)
    db.flush()

    target_name = f"{paper.id}_{uuid.uuid4().hex}.pdf"
    target_path = settings.attachments_dir / target_name

    sha256 = hashlib.sha256()
    size = 0
    with target_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            sha256.update(chunk)
            size += len(chunk)

    parsed = parse_pdf(target_path)
    candidate = extract_metadata_candidate(
        filename=file.filename,
        first_page_text=parsed.first_page_text,
        pdf_title=parsed.title,
        pdf_subject=parsed.subject,
    )

    paper.title = candidate.title
    paper.original_title = candidate.title
    paper.year = candidate.year
    paper.venue = candidate.venue
    paper.doi = candidate.doi
    paper.arxiv_id = candidate.arxiv_id
    paper.abstract = candidate.abstract
    paper.summary = candidate.abstract
    paper.language = candidate.language
    paper.needs_manual_metadata = parsed.parse_status != "ok"

    attachment = Attachment(
        paper_id=paper.id,
        original_filename=file.filename,
        stored_path=str(target_path),
        sha256=sha256.hexdigest(),
        file_size=size,
        page_count=parsed.page_count,
        extracted_text=parsed.full_text,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    return ImportPdfResponse(
        paper_draft_id=paper.id,
        attachment_id=attachment.id,
        parse_status=parsed.parse_status,
        metadata_candidate=candidate,
    )


@router.post("/papers/confirm", response_model=PaperOut)
def confirm_paper(payload: ConfirmPaperRequest, db: Session = Depends(get_db)) -> PaperOut:
    paper = db.execute(
        select(Paper)
        .options(
            selectinload(Paper.authors).selectinload(PaperAuthor.author),
            selectinload(Paper.attachments),
            selectinload(Paper.tags).selectinload(PaperTag.tag),
            selectinload(Paper.links),
        )
        .where(Paper.id == payload.paper_draft_id)
    ).scalar_one_or_none()
    if not paper:
        raise HTTPException(status_code=404, detail="paper draft not found")

    paper.status = PaperStatus.CONFIRMED.value
    if not paper.original_title:
        paper.original_title = paper.title or payload.title
    paper.title = payload.title
    paper.year = payload.year
    paper.venue = payload.venue
    paper.doi = payload.doi
    paper.arxiv_id = payload.arxiv_id
    paper.abstract = payload.abstract if payload.abstract is not None else paper.abstract
    paper.summary = (
        _normalize_summary_text(payload.summary)
        if payload.summary is not None
        else (paper.summary or paper.abstract)
    )
    paper.bibtex_override = _normalize_bibtex_override(payload.bibtex_override)
    paper.scholar_url = _normalize_scholar_url(payload.scholar_url)
    paper.summary_label = _normalize_summary_label(payload.summary_label)
    paper.language = payload.language
    paper.needs_manual_metadata = False

    _apply_authors(db, paper, payload.authors)
    _apply_tags(db, paper, payload.tags)
    db.flush()
    _cleanup_orphan_tags(db)
    rebuild_paper_fts(db, paper.id)
    db.commit()

    paper = db.execute(
        select(Paper)
        .options(
            selectinload(Paper.authors).selectinload(PaperAuthor.author),
            selectinload(Paper.attachments),
            selectinload(Paper.tags).selectinload(PaperTag.tag),
            selectinload(Paper.links),
        )
        .where(Paper.id == paper.id)
    ).scalar_one()
    return _paper_to_out(paper)


@router.get("/papers", response_model=PaperListResponse)
def list_papers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    status: str = Query(default=PaperStatus.CONFIRMED.value),
    q: str | None = None,
    sort: str = Query(default="updated_at_desc"),
    db: Session = Depends(get_db),
) -> PaperListResponse:
    filters = [Paper.status == status]
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(Paper.title.like(like), Paper.abstract.like(like), Paper.venue.like(like)))

    count_stmt = select(func.count(Paper.id)).where(and_(*filters))
    total = db.execute(count_stmt).scalar_one()

    stmt = (
        select(Paper)
        .options(
            selectinload(Paper.authors).selectinload(PaperAuthor.author),
            selectinload(Paper.attachments),
            selectinload(Paper.tags).selectinload(PaperTag.tag),
            selectinload(Paper.links),
        )
        .where(and_(*filters))
    )

    if sort == "title_asc":
        stmt = stmt.order_by(Paper.title.asc())
    elif sort == "year_desc":
        stmt = stmt.order_by(Paper.year.desc().nullslast())
    else:
        stmt = stmt.order_by(Paper.updated_at.desc())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = db.execute(stmt).scalars().all()

    return PaperListResponse(total=total, page=page, page_size=page_size, items=[_paper_to_out(item) for item in items])


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)) -> list[TagOut]:
    rows = db.execute(
        select(Tag).order_by(func.lower(Tag.name).asc())
    ).scalars().all()
    return [TagOut(id=row.id, name=row.name, color=row.color) for row in rows]


@router.get("/papers/{paper_id}", response_model=PaperOut)
def get_paper(paper_id: str, db: Session = Depends(get_db)) -> PaperOut:
    paper = db.execute(
        select(Paper)
        .options(
            selectinload(Paper.authors).selectinload(PaperAuthor.author),
            selectinload(Paper.attachments),
            selectinload(Paper.tags).selectinload(PaperTag.tag),
            selectinload(Paper.links),
        )
        .where(Paper.id == paper_id)
    ).scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="paper not found")
    return _paper_to_out(paper)


@router.post("/papers/{paper_id}", response_model=PaperOut)
def update_paper(paper_id: str, payload: UpdatePaperRequest, db: Session = Depends(get_db)) -> PaperOut:
    paper = db.execute(
        select(Paper)
        .options(
            selectinload(Paper.authors).selectinload(PaperAuthor.author),
            selectinload(Paper.attachments),
            selectinload(Paper.tags).selectinload(PaperTag.tag),
            selectinload(Paper.links),
        )
        .where(Paper.id == paper_id)
    ).scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="paper not found")

    for field in ["title", "year", "venue", "doi", "arxiv_id", "language"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(paper, field, value)
    if payload.summary is not None:
        paper.summary = _normalize_summary_text(payload.summary)
    if payload.summary_label is not None:
        paper.summary_label = _normalize_summary_label(payload.summary_label)
    if "bibtex_override" in payload.model_fields_set:
        paper.bibtex_override = _normalize_bibtex_override(payload.bibtex_override)
    if "scholar_url" in payload.model_fields_set:
        paper.scholar_url = _normalize_scholar_url(payload.scholar_url)

    if payload.authors is not None:
        _apply_authors(db, paper, payload.authors)
    if payload.tags is not None:
        _apply_tags(db, paper, payload.tags)

    db.flush()
    _cleanup_orphan_tags(db)
    rebuild_paper_fts(db, paper_id)
    db.commit()
    return _paper_to_out(paper)


@router.post("/papers/{paper_id}/attachments", response_model=AttachmentOut)
async def upload_paper_attachment(
    paper_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> AttachmentOut:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="paper not found")
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    file_ext = Path(file.filename).suffix.lower()
    suffix = file_ext or ".bin"
    target_name = f"{paper.id}_{uuid.uuid4().hex}{suffix}"
    target_path = settings.attachments_dir / target_name

    sha256 = hashlib.sha256()
    size = 0
    with target_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            sha256.update(chunk)
            size += len(chunk)

    page_count = 0
    extracted_text = None
    if file_ext == ".pdf":
        parsed = parse_pdf(target_path)
        page_count = parsed.page_count
        extracted_text = parsed.full_text

    attachment = Attachment(
        paper_id=paper.id,
        original_filename=file.filename,
        stored_path=str(target_path),
        sha256=sha256.hexdigest(),
        file_size=size,
        page_count=page_count,
        extracted_text=extracted_text,
    )
    db.add(attachment)
    db.flush()
    rebuild_paper_fts(db, paper.id)
    db.commit()
    db.refresh(attachment)

    return AttachmentOut(
        id=attachment.id,
        original_filename=attachment.original_filename,
        page_count=attachment.page_count,
        file_size=attachment.file_size,
        imported_at=attachment.imported_at,
    )


@router.post("/papers/{paper_id}/links", response_model=PaperLinkOut)
def create_paper_link(
    paper_id: str,
    payload: CreatePaperLinkRequest,
    db: Session = Depends(get_db),
) -> PaperLinkOut:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="paper not found")

    normalized_url = payload.url.strip()
    existing = db.execute(
        select(PaperLink).where(and_(PaperLink.paper_id == paper_id, PaperLink.url == normalized_url))
    ).scalar_one_or_none()
    if existing:
        return _paper_link_to_out(existing)

    label = payload.label.strip() if payload.label else None
    link = PaperLink(paper_id=paper_id, label=label or None, url=normalized_url)
    db.add(link)
    db.commit()
    db.refresh(link)
    return _paper_link_to_out(link)


@router.get("/papers/{paper_id}/links", response_model=list[PaperLinkOut])
def list_paper_links(paper_id: str, db: Session = Depends(get_db)) -> list[PaperLinkOut]:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="paper not found")

    rows = db.execute(
        select(PaperLink).where(PaperLink.paper_id == paper_id).order_by(PaperLink.created_at.desc())
    ).scalars().all()
    return [_paper_link_to_out(row) for row in rows]


@router.delete("/paper-links/{link_id}")
def delete_paper_link(link_id: int, db: Session = Depends(get_db)) -> dict:
    link = db.get(PaperLink, link_id)
    if not link:
        raise HTTPException(status_code=404, detail="link not found")

    db.delete(link)
    db.commit()
    return {"ok": True}


@router.get("/papers/{paper_id}/relations", response_model=PaperRelationsResponse)
def list_paper_relations(paper_id: str, db: Session = Depends(get_db)) -> PaperRelationsResponse:
    _ensure_confirmed_paper(paper_id, db)

    rows = db.execute(
        select(PaperRelation).where(
            or_(
                PaperRelation.source_paper_id == paper_id,
                PaperRelation.target_paper_id == paper_id,
            )
        )
    ).scalars().all()

    peer_ids = set()
    for row in rows:
        if row.source_paper_id == paper_id:
            peer_ids.add(row.target_paper_id)
        else:
            peer_ids.add(row.source_paper_id)

    peer_rows = db.execute(
        select(Paper).where(Paper.id.in_(peer_ids))
    ).scalars().all() if peer_ids else []
    peer_map = {
        row.id: {"title": row.title, "year": row.year}
        for row in peer_rows
    }

    cites: list[PaperRelationItemOut] = []
    cited_by: list[PaperRelationItemOut] = []
    related: list[PaperRelationItemOut] = []

    for row in rows:
        peer_id = row.target_paper_id if row.source_paper_id == paper_id else row.source_paper_id
        peer_meta = peer_map.get(peer_id, {})
        if row.relation_type == "cite":
            if row.source_paper_id == paper_id:
                cites.append(_relation_item_out(row, paper_id, peer_meta.get("title"), peer_meta.get("year"), False))
            else:
                cited_by.append(_relation_item_out(row, paper_id, peer_meta.get("title"), peer_meta.get("year"), True))
        elif row.relation_type == "related":
            related.append(_relation_item_out(row, paper_id, peer_meta.get("title"), peer_meta.get("year"), False))

    cites.sort(key=lambda item: item.updated_at, reverse=True)
    cited_by.sort(key=lambda item: item.updated_at, reverse=True)
    related.sort(key=lambda item: item.updated_at, reverse=True)

    return PaperRelationsResponse(
        paper_id=paper_id,
        cites=cites,
        cited_by=cited_by,
        related=related,
    )


@router.post("/papers/{paper_id}/relations", response_model=PaperRelationItemOut)
def create_paper_relation(
    paper_id: str,
    payload: CreatePaperRelationRequest,
    db: Session = Depends(get_db),
) -> PaperRelationItemOut:
    _ensure_confirmed_paper(paper_id, db)
    target_paper = _ensure_confirmed_paper(payload.target_paper_id, db)

    if paper_id == payload.target_paper_id:
        raise HTTPException(status_code=400, detail="cannot relate paper to itself")

    source_id, target_id = canonicalize_relation(paper_id, payload.target_paper_id, payload.relation_type)
    note = normalize_note(payload.note, max_len=500)

    existing = db.execute(
        select(PaperRelation).where(
            and_(
                PaperRelation.source_paper_id == source_id,
                PaperRelation.target_paper_id == target_id,
                PaperRelation.relation_type == payload.relation_type,
            )
        )
    ).scalar_one_or_none()

    relation = existing
    if not relation:
        relation = PaperRelation(
            source_paper_id=source_id,
            target_paper_id=target_id,
            relation_type=payload.relation_type,
            note=note,
        )
        db.add(relation)
        db.commit()
        db.refresh(relation)

    return _relation_item_out(
        relation,
        current_paper_id=paper_id,
        peer_title=target_paper.title,
        peer_year=target_paper.year,
        read_only=False,
    )


@router.delete("/paper-relations/{relation_id}")
def delete_paper_relation(relation_id: int, db: Session = Depends(get_db)) -> dict:
    relation = db.get(PaperRelation, relation_id)
    if not relation:
        raise HTTPException(status_code=404, detail="relation not found")

    db.delete(relation)
    db.commit()
    return {"ok": True}


@router.get("/papers/{paper_id}/relations/candidates", response_model=list[RelationCandidateOut])
def relation_candidates(
    paper_id: str,
    q: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=30),
    db: Session = Depends(get_db),
) -> list[RelationCandidateOut]:
    source_paper = _ensure_confirmed_paper(paper_id, db)
    query = " ".join(q.split()).strip() if q else None
    query = query or None

    candidates = suggest_relation_candidates(db, source_paper, query=query, limit=limit)
    existing_types_map = get_existing_relation_types(
        db,
        source_paper_id=paper_id,
        candidate_ids=[item.paper_id for item in candidates],
    )

    return [
        RelationCandidateOut(
            paper_id=item.paper_id,
            title=item.title,
            year=item.year,
            snippet=item.snippet,
            score=item.score,
            existing_types=existing_types_map.get(item.paper_id, []),
        )
        for item in candidates
    ]


@router.get("/search", response_model=SearchResponse)
def search_papers(
    q: str,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> SearchResponse:
    q = " ".join(q.strip().split())
    if not q:
        return SearchResponse(query=q, scope="meta", items=[])

    acronym_query = _query_to_acronym(q)
    like = f"%{q}%"

    exact_rows = db.execute(
        text(
            """
            SELECT DISTINCT p.id AS paper_id, p.title, p.abstract, p.updated_at
            FROM papers p
            WHERE p.status = :status
              AND (
                p.title LIKE :like
                OR p.abstract LIKE :like
              )
            ORDER BY p.updated_at DESC
            LIMIT :limit
            """
        ),
        {
            "status": PaperStatus.CONFIRMED.value,
            "like": like,
            "limit": limit,
        },
    ).mappings().all()

    results: dict[str, dict] = {}
    for row in exact_rows:
        paper_id = row["paper_id"]
        snippet_source = row["abstract"] or row["title"]
        results[paper_id] = {
            "paper_id": paper_id,
            "title": row["title"],
            "score": 100.0,
            "snippet": _build_search_snippet(snippet_source, q, acronym_query),
            "updated_at": row["updated_at"],
        }

    if len(results) < limit:
        candidate_limit = max(limit * 8, 200)
        candidate_rows = db.execute(
            text(
                """
                SELECT p.id AS paper_id, p.title, p.abstract, p.updated_at
                FROM papers p
                WHERE p.status = :status
                ORDER BY p.updated_at DESC
                LIMIT :candidate_limit
                """
            ),
            {
                "status": PaperStatus.CONFIRMED.value,
                "candidate_limit": candidate_limit,
            },
        ).mappings().all()

        query_lc = q.lower()
        threshold = _fuzzy_threshold(q)

        for row in candidate_rows:
            paper_id = row["paper_id"]
            if paper_id in results:
                continue

            title = row["title"] or ""
            abstract = row["abstract"] or ""
            abstract_slice = abstract[:4000]

            title_score = float(fuzz.partial_ratio(query_lc, title.lower())) if title else 0.0
            abstract_score = float(fuzz.partial_ratio(query_lc, abstract_slice.lower())) if abstract_slice else 0.0
            score = max(title_score, abstract_score)

            acronym_hit = False
            if acronym_query:
                acronym_hit = (
                    _find_acronym_span(title, acronym_query) is not None
                    or _find_acronym_span(abstract_slice, acronym_query) is not None
                )
                if acronym_hit:
                    score = max(score, 96.0)

            if score < threshold and not acronym_hit:
                continue

            snippet_source = abstract or title
            results[paper_id] = {
                "paper_id": paper_id,
                "title": title or None,
                "score": score,
                "snippet": _build_search_snippet(snippet_source, q, acronym_query),
                "updated_at": row["updated_at"],
            }

    sorted_rows = sorted(
        results.values(),
        key=lambda item: (float(item["score"]), str(item["updated_at"])),
        reverse=True,
    )[:limit]

    return SearchResponse(
        query=q,
        scope="meta",
        items=[
            SearchResultOut(
                paper_id=item["paper_id"],
                title=item["title"],
                score=round(float(item["score"]), 2),
                snippet=item["snippet"],
            )
            for item in sorted_rows
        ],
    )


@router.post("/papers/{paper_id}/notes", response_model=NoteOut)
def create_note(paper_id: str, payload: CreateNoteRequest, db: Session = Depends(get_db)) -> NoteOut:
    return _create_note_core(paper_id, payload, db)


@router.get("/papers/{paper_id}/notes", response_model=list[NoteOut])
def list_notes(paper_id: str, db: Session = Depends(get_db)) -> list[NoteOut]:
    return _list_notes_core(paper_id, db)


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, db: Session = Depends(get_db)) -> dict:
    _delete_note_core(note_id, db)
    return {"ok": True}


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: str, payload: UpdateNoteRequest, db: Session = Depends(get_db)) -> NoteOut:
    return _update_note_core(note_id, payload, db)


@router.post("/papers/{paper_id}/reviews", response_model=ReviewOut)
def create_review(paper_id: str, payload: CreateReviewRequest, db: Session = Depends(get_db)) -> ReviewOut:
    note_out = _create_note_core(
        paper_id,
        CreateNoteRequest(
            attachment_id=payload.attachment_id,
            page_number=payload.page_number,
            quote_text=payload.quote_text,
            note_text=payload.note_text,
        ),
        db,
    )
    return _note_out_to_review_out(note_out)


@router.get("/papers/{paper_id}/reviews", response_model=list[ReviewOut])
def list_reviews(paper_id: str, db: Session = Depends(get_db)) -> list[ReviewOut]:
    return [_note_out_to_review_out(item) for item in _list_notes_core(paper_id, db)]


@router.delete("/reviews/{review_id}")
def delete_review(review_id: str, db: Session = Depends(get_db)) -> dict:
    _delete_note_core(review_id, db, not_found_detail="review not found")
    return {"ok": True}


@router.patch("/reviews/{review_id}", response_model=ReviewOut)
def update_review(review_id: str, payload: UpdateReviewRequest, db: Session = Depends(get_db)) -> ReviewOut:
    note_out = _update_note_core(
        review_id,
        UpdateNoteRequest(
            attachment_id=payload.attachment_id,
            page_number=payload.page_number,
            quote_text=payload.quote_text,
            note_text=payload.note_text,
        ),
        db,
        not_found_detail="review not found",
    )
    return _note_out_to_review_out(note_out)


@router.get("/papers/{paper_id}/duplicates", response_model=list[DuplicateCandidate])
def list_duplicate_candidates(paper_id: str, db: Session = Depends(get_db)) -> list[DuplicateCandidate]:
    matches = find_duplicates(db, paper_id)
    return [DuplicateCandidate(paper_id=m.paper_id, title=m.title, score=m.score) for m in matches]


@router.post("/papers/{paper_id}/duplicates/resolve")
def resolve_duplicates(paper_id: str, payload: DuplicateResolveRequest, db: Session = Depends(get_db)) -> dict:
    source = db.get(Paper, paper_id)
    if not source:
        raise HTTPException(status_code=404, detail="paper not found")

    for item in payload.items:
        target = db.get(Paper, item.duplicate_paper_id)
        if not target:
            continue

        existing = db.execute(
            select(DuplicateResolution).where(
                and_(
                    DuplicateResolution.paper_id == paper_id,
                    DuplicateResolution.duplicate_paper_id == item.duplicate_paper_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.status = item.status
        else:
            db.add(
                DuplicateResolution(
                    paper_id=paper_id,
                    duplicate_paper_id=item.duplicate_paper_id,
                    status=item.status,
                )
            )

    db.commit()
    return {"ok": True}


@router.get("/papers/{paper_id}/citation", response_model=CitationResponse)
def get_citation(paper_id: str, style: str = Query(pattern="^(bibtex|apa)$"), db: Session = Depends(get_db)) -> CitationResponse:
    paper = db.execute(
        select(Paper)
        .options(selectinload(Paper.authors).selectinload(PaperAuthor.author))
        .where(Paper.id == paper_id)
    ).scalar_one_or_none()
    if not paper:
        raise HTTPException(status_code=404, detail="paper not found")

    try:
        citation = render_citation(paper, style)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CitationResponse(paper_id=paper.id, style=style, citation=citation)


@router.post("/citation/batch", response_model=CitationBatchResponse)
def citation_batch(payload: CitationBatchRequest, db: Session = Depends(get_db)) -> CitationBatchResponse:
    papers = db.execute(
        select(Paper)
        .options(selectinload(Paper.authors).selectinload(PaperAuthor.author))
        .where(Paper.id.in_(payload.paper_ids))
    ).scalars().all()

    by_id = {paper.id: paper for paper in papers}
    if payload.style == "bibtex":
        missing_manual = []
        for paper_id in payload.paper_ids:
            paper = by_id.get(paper_id)
            if not paper:
                continue
            if not paper.bibtex_override or not paper.bibtex_override.strip():
                missing_manual.append(paper.title or paper.id)
        if missing_manual:
            preview = ", ".join(missing_manual[:5])
            if len(missing_manual) > 5:
                preview = f"{preview}, ..."
            raise HTTPException(status_code=400, detail=f"manual bibtex not set: {preview}")

    items = []
    for paper_id in payload.paper_ids:
        paper = by_id.get(paper_id)
        if not paper:
            continue
        items.append(CitationResponse(paper_id=paper.id, style=payload.style, citation=render_citation(paper, payload.style)))

    return CitationBatchResponse(style=payload.style, items=items)


@router.get("/citation/export/bib")
def export_citation_bib(
    paper_ids: str = Query(min_length=1, description="Comma-separated paper ids"),
    db: Session = Depends(get_db),
) -> Response:
    requested_ids = [item.strip() for item in paper_ids.split(",") if item.strip()]
    if not requested_ids:
        raise HTTPException(status_code=400, detail="paper_ids is required")

    papers = db.execute(
        select(Paper)
        .options(selectinload(Paper.authors).selectinload(PaperAuthor.author))
        .where(Paper.id.in_(requested_ids))
    ).scalars().all()

    by_id = {paper.id: paper for paper in papers}
    missing_manual: list[str] = []
    entries: list[str] = []
    for paper_id in requested_ids:
        paper = by_id.get(paper_id)
        if not paper:
            continue
        if not paper.bibtex_override or not paper.bibtex_override.strip():
            missing_manual.append(paper.title or paper.id)
            continue
        entries.append(paper.bibtex_override.strip())

    if missing_manual:
        preview = ", ".join(missing_manual[:5])
        if len(missing_manual) > 5:
            preview = f"{preview}, ..."
        raise HTTPException(status_code=400, detail=f"manual bibtex not set: {preview}")

    if not entries:
        raise HTTPException(status_code=400, detail="no bibtex content for requested papers")

    now = datetime.now()
    filename = f"paperdesk-{now:%Y%m%d-%H%M}.bib"
    content = "\n\n".join(entries) + "\n"

    return Response(
        content=content,
        media_type="application/x-bibtex; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/backup/run", response_model=BackupItem)
def backup_run(payload: BackupRunRequest, db: Session = Depends(get_db)) -> BackupItem:
    filename = run_backup(db, kind=payload.kind)
    file_path = settings.backups_dir / filename
    stat = file_path.stat()
    return BackupItem(filename=filename, size=stat.st_size, created_at=datetime.fromtimestamp(stat.st_mtime))


@router.get("/backup/list", response_model=list[BackupItem])
def backup_list() -> list[BackupItem]:
    items = list_backups()
    return [BackupItem(filename=item["filename"], size=item["size"], created_at=item["created_at"]) for item in items]


@router.post("/backup/restore")
def backup_restore(payload: BackupRestoreRequest) -> dict:
    restore_backup(payload.filename)
    return {"ok": True}


@router.get("/attachments/{attachment_id}/file")
def download_attachment(attachment_id: str, db: Session = Depends(get_db)) -> FileResponse:
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="attachment not found")

    path = Path(attachment.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")

    media_type, _ = mimetypes.guess_type(path.name)
    resolved_media_type = media_type or "application/octet-stream"
    disposition_type = "inline" if resolved_media_type == "application/pdf" else "attachment"

    return FileResponse(
        path=str(path),
        filename=attachment.original_filename,
        media_type=resolved_media_type,
        content_disposition_type=disposition_type,
    )


def _open_external_url(url: str) -> None:
    run_result = None
    try:
        run_result = subprocess.run(["open", url], check=False, capture_output=True, text=True)
        if run_result.returncode == 0:
            return
    except Exception:
        run_result = None

    try:
        if webbrowser.open(url):
            return
    except Exception:
        pass

    detail = "failed to open external URL"
    if run_result is not None and run_result.stderr:
        detail = f"{detail}: {run_result.stderr.strip()[:200]}"
    raise HTTPException(status_code=500, detail=detail)


@router.post("/open/external")
def open_external_url(url: str = Query(min_length=1, max_length=8000, pattern=r"^https?://")) -> dict:
    _open_external_url(url)
    return {"ok": True}


@router.post("/attachments/{attachment_id}/open")
def open_attachment(
    attachment_id: str,
    request: Request,
    target: str = Query(default="preview", pattern="^(preview|browser)$"),
    db: Session = Depends(get_db),
) -> dict:
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="attachment not found")

    path = Path(attachment.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")

    if target == "preview":
        _open_external_url(path.as_uri())
    else:
        _open_external_url(str(request.url_for("download_attachment", attachment_id=attachment_id)))

    return {"ok": True}


@router.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: str, db: Session = Depends(get_db)) -> dict:
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="attachment not found")

    paper_id = attachment.paper_id
    file_path = Path(attachment.stored_path)
    if file_path.exists():
        file_path.unlink(missing_ok=True)

    db.delete(attachment)
    db.flush()
    rebuild_paper_fts(db, paper_id)
    db.commit()
    return {"ok": True}


@router.delete("/papers/{paper_id}")
def delete_paper(paper_id: str, db: Session = Depends(get_db)) -> dict:
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="paper not found")

    for attachment in paper.attachments:
        file_path = Path(attachment.stored_path)
        if file_path.exists():
            file_path.unlink(missing_ok=True)

    db.delete(paper)
    db.flush()
    _cleanup_orphan_tags(db)
    clear_paper_fts(db, paper_id)
    db.commit()
    return {"ok": True}
