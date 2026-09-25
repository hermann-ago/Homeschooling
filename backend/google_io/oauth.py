"""Google authorization for the host computer (Desktop OAuth client, PKCE, loopback).

Only the host holds Google tokens. The refresh token is DPAPI-protected under
``%LOCALAPPDATA%\\Homeschooling\\secrets``. Browsers and AI agents receive
Homeschooling device credentials instead, never Google credentials.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from security.secrets import delete_secret, read_secret, write_secret
from storage.gateway import AuthorizationRequired, GoogleUnavailable

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPES = (
    "https://www.googleapis.com/auth/drive.readonly",  # discover existing books under the root
    "https://www.googleapis.com/auth/drive.file",  # app-created files, including the workbook
)


class GoogleAuth:
    def __init__(self, secrets_dir: Path, transport: httpx.BaseTransport | None = None):
        self.dir = Path(secrets_dir)
        self.client_path = self.dir / "google-client.bin"
        self.token_path = self.dir / "google-token.bin"
        self._pending: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._access: dict | None = None
        self._http = httpx.Client(timeout=20, transport=transport)

    # ── client configuration ─────────────────────────────────────────────────
    def save_client(self, client_json: dict) -> None:
        installed = client_json.get("installed")
        if not installed or not installed.get("client_id"):
            raise ValueError("Use a Desktop app OAuth client (its JSON has an 'installed' section)")
        write_secret(self.client_path, json.dumps({"client_id": installed["client_id"],
                                                   "client_secret": installed.get("client_secret", "")}).encode())

    def _client(self) -> dict:
        raw = read_secret(self.client_path)
        if not raw:
            raise AuthorizationRequired("Add the Desktop OAuth client file in parent settings first")
        return json.loads(raw)

    @property
    def configured(self) -> bool:
        return self.client_path.exists()

    @property
    def connected(self) -> bool:
        return self.token_path.exists()

    # ── authorization code flow with PKCE ────────────────────────────────────
    def start(self, redirect_uri: str) -> str:
        client = self._client()
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(24)
        with self._lock:
            self._pending = {k: v for k, v in self._pending.items() if v["expires"] > time.time()}
            self._pending[state] = {"verifier": verifier, "redirect_uri": redirect_uri, "expires": time.time() + 600}
        return AUTH_URL + "?" + urlencode({
            "client_id": client["client_id"], "redirect_uri": redirect_uri, "response_type": "code",
            "scope": " ".join(SCOPES), "code_challenge": challenge, "code_challenge_method": "S256",
            "state": state, "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
        })

    def finish(self, state: str, code: str) -> None:
        with self._lock:
            pending = self._pending.pop(state, None)
        if not pending or pending["expires"] < time.time():
            raise AuthorizationRequired("This Google sign-in link expired; start again from parent settings")
        client = self._client()
        response = self._post(TOKEN_URL, {
            "client_id": client["client_id"], "client_secret": client["client_secret"], "code": code,
            "code_verifier": pending["verifier"], "grant_type": "authorization_code",
            "redirect_uri": pending["redirect_uri"],
        })
        body = response.json()
        if response.status_code != 200 or "refresh_token" not in body:
            raise AuthorizationRequired(body.get("error_description") or "Google did not return offline access")
        granted = set(body.get("scope", "").split())
        missing = [s for s in SCOPES if s not in granted]
        if missing:
            raise AuthorizationRequired("Google access was granted without: " + ", ".join(missing))
        write_secret(self.token_path, json.dumps({"refresh_token": body["refresh_token"],
                                                  "scope": body.get("scope")}).encode())
        self._access = {"token": body["access_token"], "expires": time.time() + int(body.get("expires_in", 3600))}

    def _post(self, url, data):
        try:
            return self._http.post(url, data=data)
        except httpx.HTTPError as error:
            raise GoogleUnavailable(f"Could not reach Google sign-in: {error}") from error

    def access_token(self, force_refresh: bool = False) -> str:
        with self._lock:
            if not force_refresh and self._access and self._access["expires"] - 60 > time.time():
                return self._access["token"]
            raw = read_secret(self.token_path)
            if not raw:
                raise AuthorizationRequired("Google is not connected; a parent must reconnect on the host computer")
            stored = json.loads(raw)
            client = self._client()
            response = self._post(TOKEN_URL, {
                "client_id": client["client_id"], "client_secret": client["client_secret"],
                "refresh_token": stored["refresh_token"], "grant_type": "refresh_token",
            })
            body = response.json() if response.content else {}
            if response.status_code in (400, 401) and body.get("error") in ("invalid_grant", "unauthorized_client"):
                raise AuthorizationRequired("Google authorization expired or was revoked; a parent must reconnect")
            if response.status_code != 200:
                raise GoogleUnavailable(f"Google sign-in returned {response.status_code}", uncertain=False)
            self._access = {"token": body["access_token"], "expires": time.time() + int(body.get("expires_in", 3600))}
            return self._access["token"]

    def disconnect(self) -> None:
        raw = read_secret(self.token_path)
        if raw:
            try:
                self._http.post(REVOKE_URL, data={"token": json.loads(raw)["refresh_token"]})
            except httpx.HTTPError:
                pass  # local removal still disconnects this computer
        delete_secret(self.token_path)
        self._access = None
