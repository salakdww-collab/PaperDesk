from io import BytesIO

import fitz
from sqlalchemy import select

import app.database as database
from app.models import Tag


def _build_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _create_confirmed_paper(client) -> str:
    payload = _build_pdf_bytes("Paper with extras")
    files = {"file": ("paper_with_extras_2026.pdf", BytesIO(payload), "application/pdf")}
    import_resp = client.post("/api/v1/import/pdf", files=files)
    assert import_resp.status_code == 200

    draft_id = import_resp.json()["paper_draft_id"]
    confirm_resp = client.post(
        "/api/v1/papers/confirm",
        json={
            "paper_draft_id": draft_id,
            "title": "Paper with extras",
            "authors": [],
            "tags": [],
        },
    )
    assert confirm_resp.status_code == 200
    return confirm_resp.json()["id"]


def test_tags_links_and_extra_attachments(client):
    paper_id = _create_confirmed_paper(client)

    update_resp = client.post(
        f"/api/v1/papers/{paper_id}",
        json={
            "tags": ["nlp", "reading-list"],
        },
    )
    assert update_resp.status_code == 200
    tag_names = sorted(item["name"] for item in update_resp.json()["tags"])
    assert tag_names == ["nlp", "reading-list"]

    link_resp = client.post(
        f"/api/v1/papers/{paper_id}/links",
        json={
            "label": "GitHub",
            "url": "https://github.com/example/repo",
        },
    )
    assert link_resp.status_code == 200
    link_id = link_resp.json()["id"]

    file_resp = client.post(
        f"/api/v1/papers/{paper_id}/attachments",
        files={"file": ("supplement.txt", BytesIO(b"supplement content"), "text/plain")},
    )
    assert file_resp.status_code == 200
    extra_attachment_id = file_resp.json()["id"]
    assert file_resp.json()["page_count"] == 0

    paper_resp = client.get(f"/api/v1/papers/{paper_id}")
    assert paper_resp.status_code == 200
    payload = paper_resp.json()
    assert any(item["name"] == "nlp" for item in payload["tags"])
    assert any(item["url"] == "https://github.com/example/repo" for item in payload["links"])
    assert any(item["id"] == extra_attachment_id for item in payload["attachments"])

    download_resp = client.get(f"/api/v1/attachments/{extra_attachment_id}/file")
    assert download_resp.status_code == 200
    assert "attachment" in download_resp.headers.get("content-disposition", "")

    delete_attachment_resp = client.delete(f"/api/v1/attachments/{extra_attachment_id}")
    assert delete_attachment_resp.status_code == 200
    assert delete_attachment_resp.json()["ok"] is True

    paper_after_attachment_delete = client.get(f"/api/v1/papers/{paper_id}")
    assert paper_after_attachment_delete.status_code == 200
    assert all(item["id"] != extra_attachment_id for item in paper_after_attachment_delete.json()["attachments"])

    delete_link_resp = client.delete(f"/api/v1/paper-links/{link_id}")
    assert delete_link_resp.status_code == 200
    assert delete_link_resp.json()["ok"] is True

    links_after_delete = client.get(f"/api/v1/papers/{paper_id}/links")
    assert links_after_delete.status_code == 200
    assert links_after_delete.json() == []


def test_can_clear_all_tags(client):
    paper_id = _create_confirmed_paper(client)

    add_tags_resp = client.post(
        f"/api/v1/papers/{paper_id}",
        json={"tags": ["keep", "remove"]},
    )
    assert add_tags_resp.status_code == 200
    assert sorted(item["name"] for item in add_tags_resp.json()["tags"]) == ["keep", "remove"]

    clear_tags_resp = client.post(
        f"/api/v1/papers/{paper_id}",
        json={"tags": []},
    )
    assert clear_tags_resp.status_code == 200
    assert clear_tags_resp.json()["tags"] == []


def test_updating_tags_removes_orphan_tag_rows(client):
    paper_id = _create_confirmed_paper(client)

    set_initial = client.post(
        f"/api/v1/papers/{paper_id}",
        json={"tags": ["Wasserstein", "generating"]},
    )
    assert set_initial.status_code == 200

    keep_only_wasserstein = client.post(
        f"/api/v1/papers/{paper_id}",
        json={"tags": ["Wasserstein"]},
    )
    assert keep_only_wasserstein.status_code == 200
    assert [item["name"] for item in keep_only_wasserstein.json()["tags"]] == ["Wasserstein"]

    with database.SessionLocal() as db:
        tag_names = sorted(db.execute(select(Tag.name)).scalars().all())
    assert tag_names == ["Wasserstein"]


def test_list_tags_endpoint_returns_existing_tags(client):
    paper_id = _create_confirmed_paper(client)
    update_resp = client.post(
        f"/api/v1/papers/{paper_id}",
        json={"tags": ["kernel", "wasserstein"]},
    )
    assert update_resp.status_code == 200

    list_tags_resp = client.get("/api/v1/tags")
    assert list_tags_resp.status_code == 200
    names = [item["name"] for item in list_tags_resp.json()]
    assert "kernel" in names
    assert "wasserstein" in names


def test_summary_label_defaults_and_can_be_updated(client):
    paper_id = _create_confirmed_paper(client)

    paper_resp = client.get(f"/api/v1/papers/{paper_id}")
    assert paper_resp.status_code == 200
    assert paper_resp.json()["summary_label"] == "Abstract"

    update_resp = client.post(
        f"/api/v1/papers/{paper_id}",
        json={"summary_label": "Summary"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["summary_label"] == "Summary"


def test_summary_is_editable_but_abstract_is_not_updated_via_update_endpoint(client):
    paper_id = _create_confirmed_paper(client)

    before_resp = client.get(f"/api/v1/papers/{paper_id}")
    assert before_resp.status_code == 200
    original_abstract = before_resp.json()["abstract"]

    update_resp = client.post(
        f"/api/v1/papers/{paper_id}",
        json={
            "summary": "Short curated summary.",
            "abstract": "This should be ignored.",
        },
    )
    assert update_resp.status_code == 200
    payload = update_resp.json()
    assert payload["summary"] == "Short curated summary."
    assert payload["abstract"] == original_abstract


def test_title_is_editable_but_original_title_is_preserved(client):
    paper_id = _create_confirmed_paper(client)

    before_resp = client.get(f"/api/v1/papers/{paper_id}")
    assert before_resp.status_code == 200
    original_title = before_resp.json()["original_title"]

    update_resp = client.post(
        f"/api/v1/papers/{paper_id}",
        json={"title": "Curated display title"},
    )
    assert update_resp.status_code == 200
    payload = update_resp.json()
    assert payload["title"] == "Curated display title"
    assert payload["original_title"] == original_title


def test_can_save_and_clear_bibtex_override_and_scholar_url(client):
    paper_id = _create_confirmed_paper(client)
    manual_bib = "@article{manual2026,\n  title={Manual Citation}\n}"
    scholar_url = "https://scholar.google.com/scholar?q=paper+with+extras"

    update_resp = client.post(
        f"/api/v1/papers/{paper_id}",
        json={
            "bibtex_override": manual_bib,
            "scholar_url": scholar_url,
        },
    )
    assert update_resp.status_code == 200
    payload = update_resp.json()
    assert payload["bibtex_override"] == manual_bib
    assert payload["scholar_url"] == scholar_url

    citation_resp = client.get(f"/api/v1/papers/{paper_id}/citation", params={"style": "bibtex"})
    assert citation_resp.status_code == 200
    assert citation_resp.json()["citation"] == manual_bib

    clear_resp = client.post(
        f"/api/v1/papers/{paper_id}",
        json={"bibtex_override": None},
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["bibtex_override"] is None

    citation_after_clear = client.get(f"/api/v1/papers/{paper_id}/citation", params={"style": "bibtex"})
    assert citation_after_clear.status_code == 400
    assert "manual bibtex not set" in citation_after_clear.json()["detail"]


def test_reject_non_scholar_url(client):
    paper_id = _create_confirmed_paper(client)

    update_resp = client.post(
        f"/api/v1/papers/{paper_id}",
        json={"scholar_url": "https://example.com/paper"},
    )
    assert update_resp.status_code == 400
    assert "scholar_url" in update_resp.json()["detail"]


def test_citation_batch_prefers_bibtex_override(client):
    paper_id = _create_confirmed_paper(client)
    manual_bib = "@article{batchmanual,\n  title={Batch Manual}\n}"
    set_override = client.post(
        f"/api/v1/papers/{paper_id}",
        json={"bibtex_override": manual_bib},
    )
    assert set_override.status_code == 200

    batch_resp = client.post(
        "/api/v1/citation/batch",
        json={"paper_ids": [paper_id], "style": "bibtex"},
    )
    assert batch_resp.status_code == 200
    items = batch_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["citation"] == manual_bib


def test_export_bib_endpoint_returns_attachment_content(client):
    paper_a = _create_confirmed_paper(client)
    paper_b = _create_confirmed_paper(client)
    manual_bib = "@article{exportmanual,\n  title={Export Manual}\n}"
    manual_bib_b = "@article{exportmanualb,\n  title={Export Manual B}\n}"
    set_override = client.post(
        f"/api/v1/papers/{paper_a}",
        json={"bibtex_override": manual_bib},
    )
    assert set_override.status_code == 200
    set_override_b = client.post(
        f"/api/v1/papers/{paper_b}",
        json={"bibtex_override": manual_bib_b},
    )
    assert set_override_b.status_code == 200

    export_resp = client.get(
        "/api/v1/citation/export/bib",
        params={"paper_ids": f"{paper_a},{paper_b}"},
    )
    assert export_resp.status_code == 200
    assert "attachment; filename=" in export_resp.headers.get("content-disposition", "")
    text = export_resp.text
    assert manual_bib in text
    assert manual_bib_b in text


def test_export_bib_endpoint_rejects_missing_manual_bibtex(client):
    paper_a = _create_confirmed_paper(client)
    paper_b = _create_confirmed_paper(client)
    manual_bib = "@article{exportmanual,\n  title={Export Manual}\n}"
    set_override = client.post(
        f"/api/v1/papers/{paper_a}",
        json={"bibtex_override": manual_bib},
    )
    assert set_override.status_code == 200

    export_resp = client.get(
        "/api/v1/citation/export/bib",
        params={"paper_ids": f"{paper_a},{paper_b}"},
    )
    assert export_resp.status_code == 400
    assert "manual bibtex not set" in export_resp.json()["detail"]
