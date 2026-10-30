"""Assembly is durable and free of generation; prepared work stays intact."""
import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from storage.backups import create_backup, verify_restore, export_excel
from storage.schema import TABLES
from tests.pdf_fixture import make_pdf
from tests.test_tutoring import seed_history


def source(key, path, role="textbook", **kw):
    return {"key": key, "path": path, "role": role, "edition": "", "position": 0,
            "is_main": role == "textbook", **kw}


def endpoint(h, subject):
    return f"/api/subjects/{subject}/book-collection"


def payload(view, **kw):
    books = [{k: b[k] for k in ("key", "document_id", "role", "edition", "position", "is_main", "companion_key", "answer_for_key")}
             for b in view["books"]]
    return {"name": view["name"], "expected_revision": view["revision"], "books": books, **kw}


def test_one_official_key_can_target_both_exact_course_parts(history):
    h,s=history
    url=endpoint(h,s['history']['id'])
    first=h.add_file(make_pdf([['Part one original exercise']]),'Books/Part one.pdf')
    second=h.add_file(make_pdf([['Part two original exercise']]),'Books/Part two.pdf')
    answers=h.add_file(make_pdf([['Official answers for both parts']]),'Books/Combined key.pdf')
    body={'name':'Two course parts','expected_revision':0,'books':[
        source('part1',first,'combined',is_main=True),source('part2',second,'combined',position=1,is_main=False),
        source('key',answers,'answer_key',position=2,is_main=False,answer_for_keys=['part1','part2'])]}
    saved=h.call('PUT',url,json=body)
    assert saved.status_code==200,saved.text
    view=saved.json();key=next(b for b in view['books'] if b['role']=='answer_key')
    assert set(key['answer_for_keys'])=={b['key'] for b in view['books'] if b['role']=='combined'}
    version=h.ctx.store.get('collection_versions',view['version_id'])
    assert len(version['manifest']['books'][2]['answer_for_ids'])==2
    # Older clients only send the first key target. Unrelated edits retain both.
    edited=payload(view,name='Renamed source collection')
    old_client=h.call('PUT',url,json=edited)
    assert old_client.status_code==200,old_client.text
    view=old_client.json()
    assert len(next(b for b in view['books'] if b['role']=='answer_key')['answer_for_keys'])==2
    bad=copy.deepcopy(body);bad['expected_revision']=view['revision'];bad['books'][2]['answer_for_keys'].append('foreign-source')
    assert h.call('PUT',url,json=bad).status_code==400
    assert h.call('GET',url).json()==view


@pytest.fixture
def history(harness, monkeypatch):
    s = seed_history(harness)
    harness.ctx.books.backfill()
    def forbidden(*args, **kw):
        raise AssertionError("Assembling books must not call a provider")
    monkeypatch.setattr(harness.ctx.ai, "generate", forbidden)
    return harness, s


def test_assembly_reuses_existing_work_persists_links_and_restores(history, tmp_path):
    h, s = history
    url = endpoint(h, s["history"]["id"])
    before = {t: copy.deepcopy(h.ctx.store.all(t)) for t in TABLES if t not in
              ("book_collections", "subject_collections", "collection_books", "collection_versions", "documents", "operation_receipts")}
    suggested = h.call("GET", url).json()
    assert suggested["revision"] == 0 and not h.ctx.store.all("book_collections")
    target = h.add_file(make_pdf([["Workbook questions"]]), "Incoming Books/Practice.pdf")
    key = h.add_file(make_pdf([["PRIVATE ANSWER CONTENT"]]), "Incoming Books/Key.pdf")
    body = payload(suggested)
    body["books"] += [source("practice", target, "workbook", position=len(body["books"]), edition="Volume 2, 2020", is_main=False),
                      source("key", key, "answer_key", position=len(body["books"]) + 1, is_main=False, answer_for_key="practice")]
    saved = h.call("PUT", url, key="assemble", json=body)
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert view["version"] == 1 and view["analysis_available"]
    key_book = next(b for b in view["books"] if b["role"] == "answer_key")
    workbook = next(b for b in view["books"] if b["key"] == key_book["answer_for_key"])
    assert workbook["edition"] == "Volume 2, 2020"
    assert workbook["companion_key"] == next(b["key"] for b in view["books"] if b["is_main"])
    assert "PRIVATE ANSWER CONTENT" not in saved.text
    assert h.call("PUT", url, key="assemble", json=body).json() == view
    assert h.call("PUT", url, json=payload(view)).json() == view  # no-op creates no new version
    assert len(h.ctx.store.all("collection_versions")) == 1
    assert before == {t: h.ctx.store.all(t) for t in before}
    h.restart()
    assert h.call("GET", url).json() == view
    backup = create_backup(h.ctx.store, tmp_path / "backups")
    restored = verify_restore(tmp_path / "backups" / backup["name"])
    assert restored["integrity"] and restored["counts"]["collection_books"] == len(view["books"])
    assert export_excel(h.ctx.store)


def test_draft_role_order_and_membership_changes_leave_prepared_records_unchanged(history):
    h, s = history
    url = endpoint(h, s["history"]["id"])
    initial = h.call("PUT", url, json=payload(h.call("GET", url).json())).json()
    before = {t: copy.deepcopy(h.ctx.store.all(t)) for t in ("subject_books", "topics", "attempts", "reviews", "checkpoints", "teacher_keys", "tutor_sessions")}
    body = payload(initial)
    body["books"][0].update(edition="Revised edition", role="combined")
    body["books"] = list(reversed(body["books"]))
    for i, b in enumerate(body["books"]):
        b["position"] = i
    changed = h.call("PUT", url, json=body)
    assert changed.status_code == 200, changed.text
    updated = changed.json()
    assert updated["version"] == 2
    retained = [b for b in payload(updated)["books"] if b["is_main"]]
    removed = h.call("PUT", url, json={**payload(updated), "books": retained})
    assert removed.status_code == 200, removed.text
    assert len(removed.json()["books"]) == 1
    assert len(h.ctx.store.all("collection_books")) == len(initial["books"])
    first_snapshot = sorted(h.ctx.store.all("collection_versions"), key=lambda r: r["number"])[0]
    assert len(first_snapshot["manifest"]["books"]) == len(initial["books"])
    assert before == {t: h.ctx.store.all(t) for t in before}


def test_simultaneous_edits_reject_stale_collection_without_losing_either_version(history):
    h, s = history
    url = endpoint(h, s["history"]["id"])
    initial = h.call("PUT", url, json=payload(h.call("GET", url).json())).json()
    def change(name):
        return h.call("PUT", url, json=payload(initial, name=name)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(change, ("Parent one", "Parent two"))) == [200, 409]
    assert len(h.ctx.store.all("collection_versions")) == 2
    assert h.call("GET", url).json()["name"] in ("Parent one", "Parent two")


def test_invalid_key_target_duplicate_pdf_and_boundary_do_not_partially_save(history):
    h, s = history
    url = endpoint(h, s["history"]["id"])
    key_path = h.add_file(make_pdf([["Key answers"]]), "Incoming Books/Key.pdf")
    bad = {"name": "History", "expected_revision": 0, "books": [source("key", key_path, "answer_key", is_main=False, answer_for_key="foreign-member")]}
    assert h.call("PUT", url, json=bad).status_code == 400
    duplicate = make_pdf([["Repeated book"]])
    p1 = h.add_file(duplicate, "Incoming Books/Copy 1.pdf")
    p2 = h.add_file(duplicate, "Incoming Books/Copy 2.pdf")
    bad["books"] = [source("one", p1), source("two", p2, position=1, is_main=False)]
    before_docs = h.ctx.store.all("documents")
    assert h.call("PUT", url, json=bad).status_code == 400
    assert h.ctx.store.all("documents") == before_docs
    assert not h.ctx.store.all("book_collections") and not h.ctx.store.all("collection_versions")
    bad["books"] = [source("escape", "../outside.pdf")]
    assert h.call("PUT", url, json=bad).status_code == 403
    bad["books"] = [source("missing", "Incoming Books/missing.pdf")]
    assert h.call("PUT", url, json=bad).status_code == 400
    assert h.call("GET", url, role="tutor").status_code == 403
    assert h.call("PUT", url, role="tutor", json=payload(h.call("GET", url).json())).status_code == 403


def test_assembling_in_test_mode_does_not_publish_real_collection(history):
    h, s = history
    url = endpoint(h, s["history"]["id"])
    mode = h.client.post("/api/test-mode", headers={"X-Homeschooling-Mode": "live"}, json={"enabled": True}).json()["token"]
    test_view = h.client.get(url, headers={"X-Homeschooling-Mode": mode}).json()
    response = h.client.put(url, headers={"X-Homeschooling-Mode": mode}, json=payload(test_view, name="Pretend collection"))
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Pretend collection"
    assert not h.ctx.store.all("book_collections")
    assert h.client.get(url, headers={"X-Homeschooling-Mode": "live"}).json()["revision"] == 0


def test_changed_pdf_at_saved_path_cannot_reuse_stale_source_identity(history):
    h, s = history
    url = endpoint(h, s["history"]["id"])
    doc = s["book"]
    h.ctx.files.resolve(doc["file_path"]).write_bytes(make_pdf([["A different edition"]]))
    body = {"name": "History", "expected_revision": 0, "books": [source("changed", doc["file_path"])]}
    response = h.call("PUT", url, json=body)
    assert response.status_code == 400 and "changed" in response.text
    assert h.ctx.store.get("documents", doc["id"])["sha256"] == doc["sha256"]
    assert not h.ctx.store.all("book_collections")
