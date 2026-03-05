from __future__ import annotations

import re
from pathlib import Path

from app.schemas import MetadataCandidate

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
ARXIV_RE = re.compile(r"\b(?:arXiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
STOP_LINE_RE = re.compile(
    r"^(abstract|摘要|keywords?|关键词|index terms?|doi\b|arxiv\b|introduction\b|1\.?\s+introduction\b)",
    re.IGNORECASE,
)
FRONT_MATTER_RE = re.compile(
    r"^(the annals of|journal of|proceedings of|vol\.?\b|volume\b|no\.?\b|pp\.?\b|doi\b|arxiv\b|received\b|revised\b|accepted\b|how to cite|copyright\b|©)",
    re.IGNORECASE,
)
ABSTRACT_START_RE = re.compile(r"^(abstract|摘要)\b[:\.\-]?\s*", re.IGNORECASE)
ABSTRACT_STOP_RE = re.compile(
    r"^(keywords?|关键词|index terms?|introduction|1\.?\s+introduction|doi\b|arxiv\b|references?|received\b|revised\b|accepted\b|how to cite)\b",
    re.IGNORECASE,
)
INVALID_PDF_TITLE_VALUES = {
    "untitled",
    "document",
    "pdf",
    "article",
    "microsoft word",
}
NOISE_LINE_RE = re.compile(r"^(page\s*\d+|\d+)\s*$", re.IGNORECASE)
AUTHOR_HINT_RE = re.compile(
    r"(@|university|institute|department|dept\.?|school|laboratory|lab\b|college)",
    re.IGNORECASE,
)
AUTHOR_NAME_LIST_RE = re.compile(
    r"^[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+)*(?:,\s*[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+)*)+$"
)
AUTHOR_AND_RE = re.compile(
    r"^[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+)*\s+and\s+[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+)*$"
)
CONTEXT_LABEL_RE = re.compile(
    r"^(advanced review|review article|research article|survey|tutorial)$",
    re.IGNORECASE,
)
SECTION_HEADING_RE = re.compile(r"^\d+(\.\d+)*\.?\s+[A-Z]", re.IGNORECASE)


def _clean_filename_stem(filename: str) -> str:
    stem = Path(filename).stem
    stem = stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem


def _normalize_line(line: str) -> str:
    normalized = re.sub(r"\s+", " ", line).strip()
    return normalized


def _is_valid_pdf_title(pdf_title: str | None) -> bool:
    if not pdf_title:
        return False
    cleaned = _normalize_line(pdf_title)
    if len(cleaned) < 4:
        return False
    return cleaned.lower() not in INVALID_PDF_TITLE_VALUES


def _looks_like_author_line(line: str) -> bool:
    lowered = line.lower()
    if AUTHOR_HINT_RE.search(lowered):
        return True
    if line.count(",") >= 2 and len(line.split()) <= 15:
        return True
    if AUTHOR_NAME_LIST_RE.match(line) and len(line.split()) <= 16:
        return True
    if AUTHOR_AND_RE.match(line) and len(line.split()) <= 16:
        return True
    if " and " in lowered and len(line.split()) <= 20:
        normalized = re.sub(r"[,;]", " ", line)
        tokens = [t for t in normalized.split() if t.lower() != "and"]
        cleaned_tokens: list[str] = []
        for token in tokens:
            token = re.sub(r"[\d*†‡]+", "", token).strip(".")
            if token:
                cleaned_tokens.append(token)
        if len(cleaned_tokens) >= 4:
            name_like = 0
            for token in cleaned_tokens:
                if not token[0].isupper():
                    break
                tail = token[1:]
                if tail and not all(ch.islower() or ch in "'-" for ch in tail):
                    break
                name_like += 1
            if name_like == len(cleaned_tokens):
                return True
    return False


def _looks_like_front_matter_line(line: str) -> bool:
    lowered = line.lower()
    if FRONT_MATTER_RE.match(line):
        return True
    if "institute of" in lowered or "wiley" in lowered:
        return True
    if lowered.startswith("c ") and "institute" in lowered:
        return True
    if re.search(r"\b(19\d{2}|20\d{2})\b", line) and (
        "vol." in lowered or "volume" in lowered or "doi" in lowered
    ):
        return True
    return False


def _looks_like_abstract_content_line(line: str) -> bool:
    if STOP_LINE_RE.match(line) or ABSTRACT_STOP_RE.match(line):
        return False
    if _looks_like_front_matter_line(line):
        return False
    if _looks_like_author_line(line):
        return False
    if CONTEXT_LABEL_RE.match(line):
        return False
    if line.endswith(":"):
        return False
    if SECTION_HEADING_RE.match(line):
        return False
    if line.isupper() and len(line.split()) <= 12:
        return False
    if len(line) < 35:
        return False
    alpha_chars = [ch for ch in line if ch.isalpha()]
    if len(alpha_chars) < 20:
        return False
    lower_ratio = sum(1 for ch in alpha_chars if ch.islower()) / len(alpha_chars)
    return lower_ratio >= 0.35


def _finalize_text(chunks: list[str], max_len: int) -> str | None:
    if not chunks:
        return None
    text = _normalize_line(" ".join(chunks))
    # Join words split across lines with soft hyphenation (e.g., theo- retical).
    text = re.sub(r"([A-Za-z])-\s+([A-Za-z])", r"\1\2", text)
    text = _normalize_line(text)
    return text[:max_len] if text else None


def _extract_title_from_first_page(first_page_text: str) -> str | None:
    if not first_page_text:
        return None

    raw_lines = first_page_text.splitlines()
    lines: list[str] = []
    for raw in raw_lines[:20]:
        line = _normalize_line(raw)
        if not line:
            continue
        if NOISE_LINE_RE.match(line):
            continue
        lines.append(line)

    if not lines:
        return None

    collected: list[str] = []
    total_len = 0
    for line in lines:
        if STOP_LINE_RE.match(line):
            if collected:
                break
            continue

        if _looks_like_front_matter_line(line) or CONTEXT_LABEL_RE.match(line):
            if collected:
                break
            continue

        if _looks_like_author_line(line):
            if collected:
                break
            continue

        collected.append(line)
        total_len += len(line) + 1
        if len(collected) >= 4 or total_len >= 600:
            break

    if not collected:
        for line in lines:
            if STOP_LINE_RE.match(line):
                continue
            if _looks_like_front_matter_line(line) or CONTEXT_LABEL_RE.match(line):
                continue
            if _looks_like_author_line(line):
                continue
            return line[:600]
        return None

    title = _normalize_line(" ".join(collected))
    return title[:600] if title else None


def _extract_abstract(first_page_text: str) -> str | None:
    if not first_page_text:
        return None

    raw_lines = first_page_text.splitlines()
    lines = [_normalize_line(line) for line in raw_lines[:80]]
    lines = [line for line in lines if line]
    if not lines:
        return None

    # Prefer content after explicit Abstract heading.
    for idx, line in enumerate(lines):
        if ABSTRACT_START_RE.match(line):
            line_without_heading = ABSTRACT_START_RE.sub("", line).strip()
            chunks: list[str] = []
            if line_without_heading:
                chunks.append(line_without_heading)

            for next_line in lines[idx + 1 :]:
                if ABSTRACT_STOP_RE.match(next_line):
                    break
                chunks.append(next_line)
                if len(" ".join(chunks)) >= 4000:
                    break

            abstract = _finalize_text(chunks, 4000)
            if abstract and len(abstract) >= 40:
                return abstract

    # Fallback: detect first likely abstract paragraph in the page head.
    start_idx: int | None = None
    for idx, line in enumerate(lines[:50]):
        if _looks_like_abstract_content_line(line):
            start_idx = idx
            break

    if start_idx is None:
        return None

    chunks: list[str] = []
    for line in lines[start_idx:]:
        if ABSTRACT_STOP_RE.match(line):
            break
        if _looks_like_front_matter_line(line) and chunks:
            break
        if SECTION_HEADING_RE.match(line):
            break
        if line.isupper() and len(line.split()) <= 12 and chunks:
            break
        chunks.append(line)
        if len(" ".join(chunks)) >= 4000:
            break

    abstract = _finalize_text(chunks, 4000)
    if abstract and len(abstract) >= 80:
        return abstract
    return None


def extract_metadata_candidate(
    filename: str,
    first_page_text: str,
    pdf_title: str | None,
    pdf_subject: str | None,
) -> MetadataCandidate:
    cleaned_name = _clean_filename_stem(filename)

    year_match = YEAR_RE.search(cleaned_name)
    year = int(year_match.group(1)) if year_match else None

    title = _normalize_line(pdf_title) if _is_valid_pdf_title(pdf_title) else None
    if not title:
        title = _extract_title_from_first_page(first_page_text)
    if not title:
        title = cleaned_name[:600] if cleaned_name else None

    doi_match = DOI_RE.search(first_page_text) if first_page_text else None
    arxiv_match = ARXIV_RE.search(first_page_text) if first_page_text else None

    abstract = _extract_abstract(first_page_text)

    venue = pdf_subject.strip()[:300] if pdf_subject else None

    return MetadataCandidate(
        title=title,
        authors=[],
        year=year,
        venue=venue,
        doi=doi_match.group(0) if doi_match else None,
        arxiv_id=arxiv_match.group(1) if arxiv_match else None,
        abstract=abstract,
        language="en",
    )


def normalize_author_name(name: str) -> str:
    lowered = name.lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered
