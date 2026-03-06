from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MetadataCandidate(BaseModel):
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None
    language: str | None = None


class ImportPdfResponse(BaseModel):
    paper_draft_id: str
    attachment_id: str
    parse_status: str
    metadata_candidate: MetadataCandidate


class ConfirmPaperRequest(BaseModel):
    paper_draft_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None
    summary: str | None = None
    bibtex_override: str | None = Field(default=None, max_length=20000)
    scholar_url: str | None = Field(default=None, max_length=2000)
    summary_label: str | None = Field(default=None, max_length=64)
    language: str | None = None
    tags: list[str] = Field(default_factory=list)


class UpdatePaperRequest(BaseModel):
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None
    summary: str | None = None
    bibtex_override: str | None = Field(default=None, max_length=20000)
    scholar_url: str | None = Field(default=None, max_length=2000)
    summary_label: str | None = Field(default=None, max_length=64)
    language: str | None = None
    tags: list[str] | None = None


class CreatePaperLinkRequest(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    url: str = Field(min_length=1, max_length=2000, pattern=r"^https?://")


class CreatePaperRelationRequest(BaseModel):
    target_paper_id: str
    relation_type: Literal["cite", "related"]
    note: str | None = Field(default=None, max_length=500)


class AuthorOut(BaseModel):
    id: int
    name: str


class AttachmentOut(BaseModel):
    id: str
    original_filename: str
    page_count: int
    file_size: int
    imported_at: datetime


class TagOut(BaseModel):
    id: int
    name: str
    color: str | None = None


class PaperLinkOut(BaseModel):
    id: int
    paper_id: str
    label: str | None = None
    url: str
    created_at: datetime


class NoteOut(BaseModel):
    id: str
    paper_id: str
    attachment_id: str | None = None
    page_number: int | None = None
    quote_text: str | None = None
    note_text: str
    created_at: datetime
    updated_at: datetime


class PaperOut(BaseModel):
    id: str
    status: str
    title: str | None = None
    original_title: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None
    summary: str | None = None
    bibtex_override: str | None = None
    scholar_url: str | None = None
    summary_label: str = "Abstract"
    language: str | None = None
    needs_manual_metadata: bool
    created_at: datetime
    updated_at: datetime
    authors: list[AuthorOut] = Field(default_factory=list)
    attachments: list[AttachmentOut] = Field(default_factory=list)
    tags: list[TagOut] = Field(default_factory=list)
    links: list[PaperLinkOut] = Field(default_factory=list)


class PaperListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[PaperOut]


class PaperRelationItemOut(BaseModel):
    relation_id: int
    peer_paper_id: str
    peer_title: str | None = None
    peer_year: int | None = None
    note: str | None = None
    updated_at: datetime
    relation_type: Literal["cite", "related"]
    read_only: bool = False


class PaperRelationsResponse(BaseModel):
    paper_id: str
    cites: list[PaperRelationItemOut] = Field(default_factory=list)
    cited_by: list[PaperRelationItemOut] = Field(default_factory=list)
    related: list[PaperRelationItemOut] = Field(default_factory=list)


class RelationCandidateOut(BaseModel):
    paper_id: str
    title: str | None = None
    year: int | None = None
    snippet: str | None = None
    score: float | None = None
    existing_types: list[Literal["cite", "related"]] = Field(default_factory=list)


class SearchResultOut(BaseModel):
    paper_id: str
    title: str | None = None
    score: float | None = None
    snippet: str | None = None


class SearchResponse(BaseModel):
    query: str
    scope: Literal["meta"]
    items: list[SearchResultOut]


class CreateNoteRequest(BaseModel):
    attachment_id: str | None = None
    page_number: int | None = None
    quote_text: str | None = None
    note_text: str


class UpdateNoteRequest(BaseModel):
    note_text: str
    quote_text: str | None = None
    page_number: int | None = None
    attachment_id: str | None = None


class CreateReviewRequest(BaseModel):
    attachment_id: str | None = None
    page_number: int | None = None
    quote_text: str | None = None
    note_text: str


class UpdateReviewRequest(BaseModel):
    note_text: str
    quote_text: str | None = None
    page_number: int | None = None
    attachment_id: str | None = None


class ReviewOut(BaseModel):
    id: str
    paper_id: str
    attachment_id: str | None = None
    page_number: int | None = None
    quote_text: str | None = None
    note_text: str
    created_at: datetime
    updated_at: datetime


class DuplicateCandidate(BaseModel):
    paper_id: str
    title: str | None = None
    score: float


class DuplicateResolveItem(BaseModel):
    duplicate_paper_id: str
    status: Literal["ignored", "confirmed_duplicate"]


class DuplicateResolveRequest(BaseModel):
    items: list[DuplicateResolveItem]


class CitationBatchRequest(BaseModel):
    paper_ids: list[str]
    style: Literal["bibtex", "apa"]


class CitationResponse(BaseModel):
    paper_id: str
    style: Literal["bibtex", "apa"]
    citation: str


class CitationBatchResponse(BaseModel):
    style: Literal["bibtex", "apa"]
    items: list[CitationResponse]


class BackupRunRequest(BaseModel):
    kind: Literal["daily", "weekly"] = "daily"


class BackupItem(BaseModel):
    filename: str
    size: int
    created_at: datetime


class BackupRestoreRequest(BaseModel):
    filename: str
