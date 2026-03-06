from app.models import Author, Paper, PaperAuthor
from app.services.citation_service import render_citation, to_apa, to_bibtex
import pytest


def test_bibtex_and_apa_output(db_session):
    paper = Paper(status="confirmed", title="Test Paper", year=2025, venue="ICML", doi="10.1000/test")
    db_session.add(paper)
    db_session.flush()

    author = Author(name="Ada Lovelace", normalized_name="ada lovelace")
    db_session.add(author)
    db_session.flush()
    db_session.add(PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=0))
    db_session.flush()
    db_session.refresh(paper)

    bib = to_bibtex(paper)
    apa = to_apa(paper)

    assert "@article" in bib
    assert "Ada Lovelace" in bib
    assert "(2025)" in apa
    assert "https://doi.org/10.1000/test" in apa


def test_bibtex_override_is_used_for_bibtex_only(db_session):
    paper = Paper(
        status="confirmed",
        title="Override Test",
        year=2024,
        venue="NeurIPS",
        bibtex_override="@article{manual2024,\n  title={Manual Entry}\n}",
    )
    db_session.add(paper)
    db_session.flush()

    bib = render_citation(paper, "bibtex")
    apa = render_citation(paper, "apa")

    assert bib.startswith("@article{manual2024")
    assert "Override Test" in apa


def test_bibtex_requires_manual_override(db_session):
    paper = Paper(status="confirmed", title="Needs Manual")
    db_session.add(paper)
    db_session.flush()

    with pytest.raises(ValueError, match="manual bibtex not set"):
        render_citation(paper, "bibtex")
