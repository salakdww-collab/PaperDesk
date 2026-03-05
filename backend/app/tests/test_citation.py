from app.models import Author, Paper, PaperAuthor
from app.services.citation_service import to_apa, to_bibtex


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
