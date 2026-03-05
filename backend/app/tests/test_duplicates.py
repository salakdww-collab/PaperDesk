from app.models import Author, Paper, PaperAuthor
from app.services.duplicate_service import find_duplicates
from app.services.metadata_service import normalize_author_name


def _add_paper(db_session, title: str, author_name: str):
    paper = Paper(status="confirmed", title=title)
    db_session.add(paper)
    db_session.flush()

    normalized = normalize_author_name(author_name)
    author = db_session.query(Author).filter(Author.normalized_name == normalized).first()
    if not author:
        author = Author(name=author_name, normalized_name=normalized)
        db_session.add(author)
        db_session.flush()

    db_session.add(PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=0))
    db_session.flush()
    return paper


def test_duplicate_detection(db_session):
    source = _add_paper(db_session, "Attention Is All You Need", "Ashish Vaswani")
    similar = _add_paper(db_session, "Attention is all you need", "A. Vaswani")
    _add_paper(db_session, "Completely Different Topic", "Someone Else")

    matches = find_duplicates(db_session, source.id, threshold=60)
    ids = [item.paper_id for item in matches]

    assert similar.id in ids
