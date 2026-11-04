"""The installed app's files: the manifest and service worker stay fresh."""


def test_install_files_are_served_fresh(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>")
    (dist / "sw.js").write_text("self.addEventListener('fetch', () => {})")
    (dist / "manifest.webmanifest").write_text('{"name": "Homeschooling"}')
    (dist / "icon-192.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr("main.FRONTEND_DIST", dist)
    from tests.conftest import Harness
    client = Harness(tmp_path).client

    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert worker.headers["content-type"].startswith("text/javascript")
    assert worker.headers["cache-control"] == "no-cache"
    manifest = client.get("/manifest.webmanifest")
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert manifest.headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/icon-192.png").headers
