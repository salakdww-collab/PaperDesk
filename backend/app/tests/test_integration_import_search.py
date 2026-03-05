from io import BytesIO

import fitz


def _build_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_import_confirm_and_search_flow(client):
    payload = _build_pdf_bytes("Transformers for local retrieval")

    files = {"file": ("transformers_2025.pdf", BytesIO(payload), "application/pdf")}
    import_resp = client.post("/api/v1/import/pdf", files=files)
    assert import_resp.status_code == 200
    draft_id = import_resp.json()["paper_draft_id"]

    confirm_resp = client.post(
        "/api/v1/papers/confirm",
        json={
            "paper_draft_id": draft_id,
            "title": "Transformers for local retrieval",
            "authors": ["Jane Doe"],
            "year": 2025,
            "abstract": "A practical insight for lightweight retrieval systems.",
            "tags": ["nlp"],
        },
    )
    assert confirm_resp.status_code == 200
    paper_id = confirm_resp.json()["id"]

    search_resp = client.get("/api/v1/search", params={"q": "Transformers"})
    assert search_resp.status_code == 200
    ids = [item["paper_id"] for item in search_resp.json()["items"]]
    assert paper_id in ids

    abstract_search = client.get("/api/v1/search", params={"q": "practical insight"})
    assert abstract_search.status_code == 200
    abstract_ids = [item["paper_id"] for item in abstract_search.json()["items"]]
    assert paper_id in abstract_ids

    note_resp = client.post(
        f"/api/v1/papers/{paper_id}/notes",
        json={"note_text": "NOTE_ONLY_TOKEN", "quote_text": "local retrieval"},
    )
    assert note_resp.status_code == 200

    note_search = client.get("/api/v1/search", params={"q": "NOTE_ONLY_TOKEN"})
    assert note_search.status_code == 200
    note_ids = [item["paper_id"] for item in note_search.json()["items"]]
    assert paper_id not in note_ids


def test_search_supports_acronym_and_fuzzy_match(client):
    payload = _build_pdf_bytes("Maximum Mean Discrepancy")

    files = {"file": ("mmd_2026.pdf", BytesIO(payload), "application/pdf")}
    import_resp = client.post("/api/v1/import/pdf", files=files)
    assert import_resp.status_code == 200
    draft_id = import_resp.json()["paper_draft_id"]

    confirm_resp = client.post(
        "/api/v1/papers/confirm",
        json={
            "paper_draft_id": draft_id,
            "title": "Maximum Mean Discrepancy for Domain Adaptation",
            "authors": ["John Doe"],
            "year": 2026,
            "abstract": "We revisit Maximum Mean Discrepancy and practical MMD training tricks.",
            "tags": ["domain-adaptation"],
        },
    )
    assert confirm_resp.status_code == 200
    paper_id = confirm_resp.json()["id"]

    acronym_search = client.get("/api/v1/search", params={"q": "MMD"})
    assert acronym_search.status_code == 200
    acronym_ids = [item["paper_id"] for item in acronym_search.json()["items"]]
    assert paper_id in acronym_ids

    fuzzy_search = client.get("/api/v1/search", params={"q": "Maxmum Mean Discrepncy"})
    assert fuzzy_search.status_code == 200
    fuzzy_ids = [item["paper_id"] for item in fuzzy_search.json()["items"]]
    assert paper_id in fuzzy_ids
