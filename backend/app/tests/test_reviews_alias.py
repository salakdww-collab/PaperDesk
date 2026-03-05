from io import BytesIO

import fitz


def _build_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _create_confirmed_paper(client) -> str:
    payload = _build_pdf_bytes("Reading-centric workflow")
    files = {"file": ("reading_2026.pdf", BytesIO(payload), "application/pdf")}
    import_resp = client.post("/api/v1/import/pdf", files=files)
    assert import_resp.status_code == 200

    draft_id = import_resp.json()["paper_draft_id"]
    confirm_resp = client.post(
        "/api/v1/papers/confirm",
        json={
            "paper_draft_id": draft_id,
            "title": "Reading-centric workflow",
            "authors": [],
            "tags": [],
        },
    )
    assert confirm_resp.status_code == 200
    return confirm_resp.json()["id"]


def test_review_alias_endpoints_are_equivalent_to_notes(client):
    paper_id = _create_confirmed_paper(client)

    create_review = client.post(
        f"/api/v1/papers/{paper_id}/reviews",
        json={"note_text": "My review", "quote_text": "Important quote", "page_number": 1},
    )
    assert create_review.status_code == 200
    review_id = create_review.json()["id"]

    list_reviews = client.get(f"/api/v1/papers/{paper_id}/reviews")
    assert list_reviews.status_code == 200
    assert len(list_reviews.json()) == 1

    list_notes = client.get(f"/api/v1/papers/{paper_id}/notes")
    assert list_notes.status_code == 200
    assert list_notes.json()[0]["id"] == review_id

    update_review = client.patch(
        f"/api/v1/reviews/{review_id}",
        json={"note_text": "My updated review"},
    )
    assert update_review.status_code == 200
    assert update_review.json()["note_text"] == "My updated review"

    list_notes_after_update = client.get(f"/api/v1/papers/{paper_id}/notes")
    assert list_notes_after_update.status_code == 200
    assert list_notes_after_update.json()[0]["note_text"] == "My updated review"

    delete_review = client.delete(f"/api/v1/reviews/{review_id}")
    assert delete_review.status_code == 200

    list_reviews_after = client.get(f"/api/v1/papers/{paper_id}/reviews")
    assert list_reviews_after.status_code == 200
    assert list_reviews_after.json() == []
