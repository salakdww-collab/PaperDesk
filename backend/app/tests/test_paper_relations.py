from __future__ import annotations

from io import BytesIO

import fitz


def _build_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _import_draft(client, title_token: str) -> str:
    payload = _build_pdf_bytes(f"{title_token} content")
    files = {"file": (f"{title_token}.pdf", BytesIO(payload), "application/pdf")}
    resp = client.post("/api/v1/import/pdf", files=files)
    assert resp.status_code == 200
    return resp.json()["paper_draft_id"]


def _create_confirmed_paper(client, title: str, abstract: str, year: int = 2026) -> str:
    draft_id = _import_draft(client, title.replace(" ", "_").lower())
    resp = client.post(
        "/api/v1/papers/confirm",
        json={
            "paper_draft_id": draft_id,
            "title": title,
            "authors": [],
            "year": year,
            "abstract": abstract,
            "tags": [],
        },
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def _find_group_item(groups: dict, group_name: str, peer_paper_id: str) -> dict:
    for item in groups[group_name]:
        if item["peer_paper_id"] == peer_paper_id:
            return item
    raise AssertionError(f"peer {peer_paper_id} not found in {group_name}")


def test_create_group_and_cited_by_read_only(client):
    paper_a = _create_confirmed_paper(client, "Kernel Two-Sample Test", "MMD based two-sample testing.")
    paper_b = _create_confirmed_paper(client, "Domain Adaptation With MMD", "Maximum Mean Discrepancy objective.")
    paper_c = _create_confirmed_paper(client, "Permutation Testing", "Permutation tests with finite samples.")

    cite_resp = client.post(
        f"/api/v1/papers/{paper_a}/relations",
        json={"target_paper_id": paper_b, "relation_type": "cite", "note": "core citation"},
    )
    assert cite_resp.status_code == 200

    related_resp = client.post(
        f"/api/v1/papers/{paper_a}/relations",
        json={"target_paper_id": paper_b, "relation_type": "related", "note": "similar method"},
    )
    assert related_resp.status_code == 200

    cited_by_resp = client.post(
        f"/api/v1/papers/{paper_c}/relations",
        json={"target_paper_id": paper_a, "relation_type": "cite", "note": "builds on paper A"},
    )
    assert cited_by_resp.status_code == 200

    list_resp = client.get(f"/api/v1/papers/{paper_a}/relations")
    assert list_resp.status_code == 200
    payload = list_resp.json()

    cite_item = _find_group_item(payload, "cites", paper_b)
    related_item = _find_group_item(payload, "related", paper_b)
    cited_by_item = _find_group_item(payload, "cited_by", paper_c)

    assert cite_item["relation_type"] == "cite"
    assert cite_item["read_only"] is False
    assert related_item["relation_type"] == "related"
    assert related_item["read_only"] is False
    assert cited_by_item["relation_type"] == "cite"
    assert cited_by_item["read_only"] is True


def test_related_canonical_and_same_type_idempotent(client):
    paper_a = _create_confirmed_paper(client, "A paper", "Alpha.")
    paper_b = _create_confirmed_paper(client, "B paper", "Beta.")

    first = client.post(
        f"/api/v1/papers/{paper_a}/relations",
        json={"target_paper_id": paper_b, "relation_type": "related", "note": "first note"},
    )
    assert first.status_code == 200
    first_payload = first.json()

    second = client.post(
        f"/api/v1/papers/{paper_b}/relations",
        json={"target_paper_id": paper_a, "relation_type": "related", "note": "second note should be ignored"},
    )
    assert second.status_code == 200
    second_payload = second.json()

    assert first_payload["relation_id"] == second_payload["relation_id"]
    assert second_payload["note"] == "first note"

    list_a = client.get(f"/api/v1/papers/{paper_a}/relations").json()
    list_b = client.get(f"/api/v1/papers/{paper_b}/relations").json()
    assert len(list_a["related"]) == 1
    assert len(list_b["related"]) == 1


def test_reject_self_and_draft_target(client):
    confirmed_id = _create_confirmed_paper(client, "Confirmed source", "source abstract")
    draft_id = _import_draft(client, "draft_target")

    self_resp = client.post(
        f"/api/v1/papers/{confirmed_id}/relations",
        json={"target_paper_id": confirmed_id, "relation_type": "cite"},
    )
    assert self_resp.status_code == 400

    draft_resp = client.post(
        f"/api/v1/papers/{confirmed_id}/relations",
        json={"target_paper_id": draft_id, "relation_type": "cite"},
    )
    assert draft_resp.status_code == 400


def test_delete_updates_groups_and_candidate_existing_types(client):
    source_id = _create_confirmed_paper(client, "Graph Kernels", "Kernel methods in graphs")
    target_id = _create_confirmed_paper(client, "Kernel Mean Embedding", "Mean embeddings and MMD")

    cite_resp = client.post(
        f"/api/v1/papers/{source_id}/relations",
        json={"target_paper_id": target_id, "relation_type": "cite"},
    )
    assert cite_resp.status_code == 200
    cite_relation_id = cite_resp.json()["relation_id"]

    related_resp = client.post(
        f"/api/v1/papers/{source_id}/relations",
        json={"target_paper_id": target_id, "relation_type": "related"},
    )
    assert related_resp.status_code == 200
    related_relation_id = related_resp.json()["relation_id"]

    before = client.get(
        f"/api/v1/papers/{source_id}/relations/candidates",
        params={"q": "Kernel Mean Embedding", "limit": 10},
    )
    assert before.status_code == 200
    target_before = next((item for item in before.json() if item["paper_id"] == target_id), None)
    assert target_before is not None
    assert sorted(target_before["existing_types"]) == ["cite", "related"]

    delete_related = client.delete(f"/api/v1/paper-relations/{related_relation_id}")
    assert delete_related.status_code == 200
    assert delete_related.json()["ok"] is True

    groups_after_related = client.get(f"/api/v1/papers/{source_id}/relations").json()
    assert len(groups_after_related["cites"]) == 1
    assert len(groups_after_related["related"]) == 0

    middle = client.get(
        f"/api/v1/papers/{source_id}/relations/candidates",
        params={"q": "Kernel Mean Embedding", "limit": 10},
    )
    target_middle = next((item for item in middle.json() if item["paper_id"] == target_id), None)
    assert target_middle is not None
    assert target_middle["existing_types"] == ["cite"]

    delete_cite = client.delete(f"/api/v1/paper-relations/{cite_relation_id}")
    assert delete_cite.status_code == 200

    after = client.get(
        f"/api/v1/papers/{source_id}/relations/candidates",
        params={"q": "Kernel Mean Embedding", "limit": 10},
    )
    target_after = next((item for item in after.json() if item["paper_id"] == target_id), None)
    assert target_after is not None
    assert target_after["existing_types"] == []


def test_candidates_exclude_self_and_draft(client):
    source_id = _create_confirmed_paper(client, "Source Paper", "source abstract")
    confirmed_peer = _create_confirmed_paper(client, "Confirmed Peer", "peer abstract")
    _import_draft(client, "draft_only_paper")

    resp = client.get(f"/api/v1/papers/{source_id}/relations/candidates", params={"limit": 10})
    assert resp.status_code == 200
    candidate_ids = [item["paper_id"] for item in resp.json()]

    assert source_id not in candidate_ids
    assert confirmed_peer in candidate_ids
