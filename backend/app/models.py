from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PaperStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(16), default=PaperStatus.DRAFT.value, nullable=False)
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    original_title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_label: Mapped[str] = mapped_column(String(64), nullable=False, default="Abstract")
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    needs_manual_metadata: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    authors: Mapped[list[PaperAuthor]] = relationship("PaperAuthor", back_populates="paper", cascade="all, delete-orphan")
    attachments: Mapped[list[Attachment]] = relationship("Attachment", back_populates="paper", cascade="all, delete-orphan")
    notes: Mapped[list[Note]] = relationship("Note", back_populates="paper", cascade="all, delete-orphan")
    tags: Mapped[list[PaperTag]] = relationship("PaperTag", back_populates="paper", cascade="all, delete-orphan")
    links: Mapped[list[PaperLink]] = relationship("PaperLink", back_populates="paper", cascade="all, delete-orphan")
    collections: Mapped[list[CollectionItem]] = relationship("CollectionItem", back_populates="paper", cascade="all, delete-orphan")


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)

    papers: Mapped[list[PaperAuthor]] = relationship("PaperAuthor", back_populates="author")


class PaperAuthor(Base):
    __tablename__ = "paper_authors"
    __table_args__ = (UniqueConstraint("paper_id", "author_id", name="uq_paper_author"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("authors.id", ondelete="CASCADE"), nullable=False)
    author_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    paper: Mapped[Paper] = relationship("Paper", back_populates="authors")
    author: Mapped[Author] = relationship("Author", back_populates="papers")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    paper: Mapped[Paper] = relationship("Paper", back_populates="attachments")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)

    papers: Mapped[list[PaperTag]] = relationship("PaperTag", back_populates="tag")


class PaperTag(Base):
    __tablename__ = "paper_tags"
    __table_args__ = (UniqueConstraint("paper_id", "tag_id", name="uq_paper_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)

    paper: Mapped[Paper] = relationship("Paper", back_populates="tags")
    tag: Mapped[Tag] = relationship("Tag", back_populates="papers")


class PaperLink(Base):
    __tablename__ = "paper_links"
    __table_args__ = (UniqueConstraint("paper_id", "url", name="uq_paper_link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    paper: Mapped[Paper] = relationship("Paper", back_populates="links")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    attachment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    paper: Mapped[Paper] = relationship("Paper", back_populates="notes")


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    papers: Mapped[list[CollectionItem]] = relationship("CollectionItem", back_populates="collection")


class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (UniqueConstraint("collection_id", "paper_id", name="uq_collection_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(Integer, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)

    collection: Mapped[Collection] = relationship("Collection", back_populates="papers")
    paper: Mapped[Paper] = relationship("Paper", back_populates="collections")


class DuplicateResolution(Base):
    __tablename__ = "duplicate_resolutions"
    __table_args__ = (UniqueConstraint("paper_id", "duplicate_paper_id", name="uq_duplicate_resolution"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    duplicate_paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PaperRelation(Base):
    __tablename__ = "paper_relations"
    __table_args__ = (
        UniqueConstraint("source_paper_id", "target_paper_id", "relation_type", name="uq_paper_relation"),
        CheckConstraint("source_paper_id <> target_paper_id", name="ck_paper_relation_not_self"),
        CheckConstraint("relation_type IN ('cite', 'related')", name="ck_paper_relation_type"),
        Index("idx_rel_source_type", "source_paper_id", "relation_type"),
        Index("idx_rel_target_type", "target_paper_id", "relation_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    target_paper_id: Mapped[str] = mapped_column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
