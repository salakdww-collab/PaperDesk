from io import BytesIO

import fitz


def _build_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _create_confirmed_paper_with_attachment(client) -> tuple[str, str]:
    payload = _build_pdf_bytes("Open me")
    files = {"file": ("open_me_2026.pdf", BytesIO(payload), "application/pdf")}
    import_resp = client.post("/api/v1/import/pdf", files=files)
    assert import_resp.status_code == 200

    draft_id = import_resp.json()["paper_draft_id"]
    attachment_id = import_resp.json()["attachment_id"]
    confirm_resp = client.post(
        "/api/v1/papers/confirm",
        json={
            "paper_draft_id": draft_id,
            "title": "Open me",
            "authors": [],
            "tags": [],
        },
    )
    assert confirm_resp.status_code == 200
    return confirm_resp.json()["id"], attachment_id


def test_open_attachment_endpoint(client, monkeypatch):
    _, attachment_id = _create_confirmed_paper_with_attachment(client)

    called = {"count": 0}

    class _RunResult:
        returncode = 0
        stderr = ""

    def fake_run(args, check=False, **kwargs):
        called["count"] += 1
        return _RunResult()

    monkeypatch.setattr("app.api.routes.subprocess.run", fake_run)

    resp_preview = client.post(f"/api/v1/attachments/{attachment_id}/open", params={"target": "preview"})
    assert resp_preview.status_code == 200
    assert resp_preview.json()["ok"] is True

    resp_browser = client.post(f"/api/v1/attachments/{attachment_id}/open", params={"target": "browser"})
    assert resp_browser.status_code == 200
    assert resp_browser.json()["ok"] is True

    assert called["count"] == 2

    file_resp = client.get(f"/api/v1/attachments/{attachment_id}/file")
    assert file_resp.status_code == 200
    assert "inline" in file_resp.headers.get("content-disposition", "")


def test_open_external_url_endpoint(client, monkeypatch):
    called = {"count": 0, "url": ""}

    class _RunResult:
        returncode = 0
        stderr = ""

    def fake_run(args, check=False, **kwargs):
        called["count"] += 1
        called["url"] = args[1]
        return _RunResult()

    monkeypatch.setattr("app.api.routes.subprocess.run", fake_run)

    resp = client.post("/api/v1/open/external", params={"url": "https://scholar.google.com/scholar?q=kernel+methods"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert called["count"] == 1
    assert called["url"].startswith("https://scholar.google.")
