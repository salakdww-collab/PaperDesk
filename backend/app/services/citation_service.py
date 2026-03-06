from __future__ import annotations

import re

from app.models import Paper



def _author_names(paper: Paper) -> list[str]:
    rows = sorted(paper.authors, key=lambda x: x.author_order)
    return [row.author.name for row in rows if row.author]


def _safe_key(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", text)


def to_bibtex(paper: Paper) -> str:
    authors = _author_names(paper)
    first_author = authors[0] if authors else "unknown"
    year = paper.year or 1900
    key = f"{_safe_key(first_author.split()[-1])}{year}"

    fields = {
        "title": paper.title or "Untitled",
        "author": " and ".join(authors) if authors else "Unknown",
        "year": str(year),
        "journal": paper.venue or "",
        "doi": paper.doi or "",
    }
    body = "\n".join([f"  {k} = {{{v}}}," for k, v in fields.items() if v])
    return f"@article{{{key},\n{body}\n}}"


def to_apa(paper: Paper) -> str:
    authors = _author_names(paper)
    if authors:
        formatted_authors = ", ".join(authors)
    else:
        formatted_authors = "Unknown"

    year_text = str(paper.year) if paper.year else "n.d."
    title = paper.title or "Untitled"
    venue = paper.venue or ""
    doi_text = f" https://doi.org/{paper.doi}" if paper.doi else ""

    venue_part = f" *{venue}*." if venue else ""
    return f"{formatted_authors} ({year_text}). {title}.{venue_part}{doi_text}".strip()


def render_citation(paper: Paper, style: str) -> str:
    if style == "bibtex":
        if paper.bibtex_override and paper.bibtex_override.strip():
            return paper.bibtex_override.strip()
        raise ValueError("manual bibtex not set")
    if style == "apa":
        return to_apa(paper)
    raise ValueError(f"unsupported style: {style}")
