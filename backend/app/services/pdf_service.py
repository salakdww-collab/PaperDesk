from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass
class PdfParseResult:
    page_count: int
    full_text: str
    first_page_text: str
    title: str | None
    subject: str | None
    parse_status: str



def parse_pdf(file_path: Path) -> PdfParseResult:
    try:
        with fitz.open(file_path) as doc:
            page_count = doc.page_count
            full_text_chunks: list[str] = []
            first_page_text = ""
            for i, page in enumerate(doc):
                text = page.get_text("text") or ""
                if i == 0:
                    first_page_text = text
                full_text_chunks.append(text)

            metadata = doc.metadata or {}
            title = metadata.get("title")
            subject = metadata.get("subject")

        return PdfParseResult(
            page_count=page_count,
            full_text="\n".join(full_text_chunks),
            first_page_text=first_page_text,
            title=title,
            subject=subject,
            parse_status="ok",
        )
    except Exception:
        return PdfParseResult(
            page_count=0,
            full_text="",
            first_page_text="",
            title=None,
            subject=None,
            parse_status="failed",
        )
