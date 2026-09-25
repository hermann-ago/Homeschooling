import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from google_io.drive import DriveClient
from google_io.oauth import SCOPES, GoogleAuth
from google_io.rest import GoogleRest
from google_io.sheets import SheetsClient
from storage.gateway import AuthorizationRequired, GoogleUnavailable, OutsideBoundary


class StaticAuth:
    def __init__(self):
        self.refreshes = 0

    def access_token(self, force_refresh=False):
        if force_refresh:
            self.refreshes += 1
        return f"token-{self.refreshes}"


def rest_with(handler):
    return GoogleRest(StaticAuth(), transport=httpx.MockTransport(handler), sleep=lambda _: None)


def test_pkce_authorization_and_refresh(tmp_path):
    seen = {}

    def handler(request):
        form = parse_qs(request.content.decode())
        seen.setdefault("grants", []).append(form["grant_type"][0])
        if form["grant_type"][0] == "authorization_code":
            seen["verifier"] = form["code_verifier"][0]
            return httpx.Response(200, json={"access_token": "a1", "refresh_token": "r1", "expires_in": 1,
                                             "scope": " ".join(SCOPES)})
        return httpx.Response(200, json={"access_token": "a2", "expires_in": 3600})

    auth = GoogleAuth(tmp_path, transport=httpx.MockTransport(handler))
    auth.save_client({"installed": {"client_id": "id.apps.googleusercontent.com", "client_secret": "s"}})
    url = auth.start("http://127.0.0.1:8000/api/google/oauth/callback")
    query = parse_qs(urlparse(url).query)
    assert query["code_challenge_method"] == ["S256"] and query["access_type"] == ["offline"]
    assert set(query["scope"][0].split()) == set(SCOPES)
    auth.finish(query["state"][0], "code-123")
    assert len(seen["verifier"]) >= 43
    assert b"r1" not in (tmp_path / "google-token.bin").read_bytes()[:6]  # marker precedes protected payload
    assert auth.access_token() == "a2"  # the first token expired, so it refreshed
    with pytest.raises(AuthorizationRequired):
        auth.finish(query["state"][0], "code-again")  # a state is single use


def test_revoked_refresh_token_requires_parent_reconnect(tmp_path):
    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})
    auth = GoogleAuth(tmp_path, transport=httpx.MockTransport(handler))
    auth.save_client({"installed": {"client_id": "id", "client_secret": "s"}})
    from security.secrets import write_secret
    write_secret(tmp_path / "google-token.bin", json.dumps({"refresh_token": "r"}).encode())
    with pytest.raises(AuthorizationRequired):
        auth.access_token()


def test_reads_retry_but_uncertain_writes_are_not_resent():
    calls = {"get": 0, "post": 0}

    def handler(request):
        if request.method == "GET":
            calls["get"] += 1
            if calls["get"] < 3:
                return httpx.Response(429, json={"error": {"message": "slow down"}})
            return httpx.Response(200, json={"valueRanges": [{"values": [["id", "revision"], [1, 2]]}]})
        calls["post"] += 1
        return httpx.Response(503, json={"error": {"message": "backend"}})

    sheets = SheetsClient(rest_with(handler), "sheet123")
    assert sheets.get_values(["'Children'!A:B"]) == [[["id", "revision"], ["1", "2"]]]
    assert calls["get"] == 3
    with pytest.raises(GoogleUnavailable) as uncertain:
        sheets.batch_update([{"appendCells": {}}])
    assert uncertain.value.uncertain and calls["post"] == 1


def test_expired_access_token_is_refreshed_once():
    auth = StaticAuth()

    def handler(request):
        if request.headers["Authorization"] == "Bearer token-0":
            return httpx.Response(401)
        return httpx.Response(200, json={"sheets": [{"properties": {"title": "Children", "sheetId": 7}}]})

    rest = GoogleRest(auth, transport=httpx.MockTransport(handler), sleep=lambda _: None)
    assert SheetsClient(rest, "s").metadata() == {"Children": 7}
    assert auth.refreshes == 1


def test_drive_boundary_walks_parents():
    parents = {"inside": ["books"], "books": ["root"], "outside": ["other"], "other": []}

    def handler(request):
        file_id = request.url.path.rsplit("/", 1)[-1]
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, content=b"%PDF-1.4")
        return httpx.Response(200, json={"id": file_id, "parents": parents[file_id], "mimeType": "application/pdf"})

    drive = DriveClient(rest_with(handler), "root")
    assert drive.download("inside") == b"%PDF-1.4"
    with pytest.raises(OutsideBoundary):
        drive.download("outside")
