"""Narration for reviewed passages.

* Timings come only from the provider (Google TTS SSML-mark timepoints) or from
  validated cached manifests. Tracks whose passage hash or sentence count do not
  match are played, if at all, without highlighting; timings are never guessed.
* Every generation reserves characters in the shared HomeTutor ledger at
  ``%LOCALAPPDATA%\\HomeTutor\\google\\<project>\\usage.json`` (the file the
  History tools already use). The monthly guard is 150,000 characters; going
  over it requires an explicit parent approval for that request.
* A reservation for a request whose outcome is uncertain stays counted and is
  never retried automatically.
* Legacy ElevenLabs audio (Robin Hood) is preserved and never regenerated here.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

MONTHLY_LIMIT = 150_000
DEFAULT_VOICE = "en-US-Neural2-J"
DEFAULT_RATE = 0.9
MAX_SSML_BYTES = 4800
TTS_URL = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"


class LedgerError(RuntimeError):
    pass


class UsageLedger:
    """Python twin of tools/tts_usage.mjs, sharing its file, format and lock."""

    def __init__(self, root: Path, project: str):
        if not re.fullmatch(r"[a-z0-9-]+", project or ""):
            raise LedgerError("Invalid Google project ID")
        self.path = Path(root) / "google" / project / "usage.json"

    def _load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": 2, "months": {}, "imports": []}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("schema_version") != 2 or not isinstance(value.get("months"), dict) \
                or not isinstance(value.get("imports"), list):
            raise LedgerError("Usage ledger is invalid; no request allowed.")
        for month in value["months"].values():
            if not isinstance(month.get("characters"), (int, float)) or month["characters"] < 0:
                raise LedgerError("Invalid usage total")
        return value

    def _write(self, value: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

    def _locked(self, work):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(self.path.name + ".lock")
        for _ in range(100):
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                time.sleep(0.05)
        else:
            raise LedgerError("Usage ledger is locked by another narration job")
        try:
            os.write(fd, str(os.getpid()).encode())
            return work()
        finally:
            os.close(fd)
            lock.unlink(missing_ok=True)

    def used(self, month: str) -> int:
        return int(self._load()["months"].get(month, {}).get("characters", 0))

    def reserve(self, month: str, request_id: str, characters: int, overage_approval: dict | None = None) -> int:
        if not isinstance(characters, int) or characters < 1:
            raise LedgerError("Invalid request character count")

        def work():
            value = self._load()
            entry = value["months"].setdefault(month, {"characters": 0, "requests": {}})
            entry.setdefault("requests", {})
            if request_id in entry["requests"]:
                raise LedgerError(f"Request {request_id} already reserved or sent; reconcile its cache before retrying.")
            total = entry["characters"] + characters
            if total > MONTHLY_LIMIT:
                approved = overage_approval and overage_approval.get("approved_by_parent") \
                    and total <= MONTHLY_LIMIT + int(overage_approval.get("extra_characters", 0))
                if not approved:
                    raise LedgerError(f"Local monthly ceiling exceeded ({total} > {MONTHLY_LIMIT}); no request sent. "
                                      "Paid overage needs explicit parent approval.")
                entry.setdefault("overage_approvals", []).append({**overage_approval, "request": request_id,
                                                                  "at": _now()})
            entry["characters"] = total
            entry["requests"][request_id] = {"characters": characters, "status": "reserved", "at": _now()}
            self._write(value)
            return total
        return self._locked(work)

    def mark(self, month: str, request_id: str, status: str):
        def work():
            value = self._load()
            request = value["months"].get(month, {}).get("requests", {}).get(request_id)
            if not request:
                raise LedgerError("Missing usage reservation")
            request["status"] = status
            self._write(value)
        self._locked(work)


def _now():
    return datetime.now(timezone.utc).isoformat()


def month_key(moment: datetime | None = None) -> str:
    return (moment or datetime.now(timezone.utc)).strftime("%Y-%m")


def cache_key(passage_sha: str, provider: str, voice: str, rate: float) -> str:
    return hashlib.sha256(json.dumps([passage_sha, provider, voice, round(rate, 3), 2]).encode()).hexdigest()


def validate_manifest(manifest: dict, passage_sha: str, sentence_count: int) -> tuple[bool, str]:
    """A manifest synchronises only with the exact passage it was generated for."""
    if manifest.get("passageHash") != passage_sha:
        return False, "Audio was generated for a different passage text"
    if manifest.get("sentenceCount") != sentence_count:
        return False, "Audio sentence count does not match the passage"
    covered = 0
    for track in manifest.get("tracks", []):
        starts = track.get("sentenceStarts") or []
        if track.get("startSentence") != covered or not starts:
            return False, "Audio tracks do not cover every sentence in order"
        if any(b < a for a, b in zip(starts, starts[1:])):
            return False, "Audio timings are not increasing"
        covered += len(starts)
    if covered != sentence_count:
        return False, "Audio timings do not cover every sentence"
    return True, "ok"


def _ssml_chunks(sentences: list[dict]) -> list[tuple[int, int, str, int]]:
    """(first sentence index, sentence count, SSML, characters) chunks under the request size limit."""
    chunks, current, first, characters = [], [], 0, 0
    for index, sentence in enumerate(sentences):
        piece = f'<mark name="s{index}"/>{html.escape(sentence["text"], quote=False)} '
        if current and len("<speak>" + "".join(current) + piece + "</speak>") > MAX_SSML_BYTES:
            chunks.append((first, len(current), "<speak>" + "".join(current) + "</speak>", characters))
            current, first, characters = [], index, 0
        current.append(piece)
        characters += len(sentence["text"])
    if current:
        chunks.append((first, len(current), "<speak>" + "".join(current) + "</speak>", characters))
    return chunks


def gcloud_token() -> str:
    """Access token from the host's existing gcloud login (kept outside synced folders)."""
    command = "gcloud.cmd" if os.name == "nt" else "gcloud"
    result = subprocess.run([command, "auth", "print-access-token"], capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or not result.stdout.strip():
        raise LedgerError("gcloud is not signed in on the host computer; narration needs a parent to sign in")
    return result.stdout.strip()


class GoogleTTS:
    provider = "google-neural2"

    def __init__(self, project: str, token_source=gcloud_token, http=None):
        import httpx
        self.project = project
        self.token_source = token_source
        self.http = http or httpx.Client(timeout=90)

    def synthesize(self, ssml: str, voice: str, rate: float) -> dict:
        response = self.http.post(TTS_URL, headers={"Authorization": f"Bearer {self.token_source()}",
                                                    "x-goog-user-project": self.project}, json={
            "input": {"ssml": ssml}, "voice": {"languageCode": voice[:5], "name": voice},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": rate}, "enableTimePointing": ["SSML_MARK"]})
        if response.status_code != 200:
            raise RuntimeError(f"Google TTS returned {response.status_code}: {response.text[:200]}")
        return response.json()


def generate(ctx, tx, topic: dict, passage: dict, *, voice: str, rate: float, engine=None,
             overage_approval: dict | None = None, dry_run: bool = False) -> dict:
    """Generate one narrator for a verified passage, reusing a validated cache."""
    if passage["status"] != "verified":
        raise ValueError("Review the passage against the original pages before generating narration")
    key = cache_key(passage["passage_sha256"], "google-neural2", voice, rate)
    existing = tx.get("audio_tracks", key)
    if existing and existing["status"] == "ready":
        return {"track_id": key, "reused": True, "characters": 0}
    sentences = passage["sentences"]
    chunks = _ssml_chunks(sentences)
    characters = sum(c for _, _, _, c in chunks)
    project = ctx.config.get("tts", {}).get("project")
    from config import home_tutor_dir
    ledger = UsageLedger(home_tutor_dir(), project)
    month = month_key()
    estimate = {"track_id": key, "characters": characters, "parts": len(chunks), "month": month,
                "used_this_month": ledger.used(month), "monthly_limit": MONTHLY_LIMIT, "voice": voice, "rate": rate}
    if dry_run:
        return {**estimate, "dry_run": True}
    engine = engine or GoogleTTS(project)
    tracks = []
    for part, (first, count, ssml, part_characters) in enumerate(chunks, start=1):
        request_id = f"{key[:24]}-part-{part}"
        ledger.reserve(month, request_id, part_characters, overage_approval)
        try:
            response = engine.synthesize(ssml, voice, rate)
        except Exception:
            ledger.mark(month, request_id, "uncertain")  # stays counted; never auto-retried
            raise
        marks = {tp["markName"]: tp["timeSeconds"] for tp in response.get("timepoints", [])}
        if any(f"s{index}" not in marks for index in range(first, first + count)):
            ledger.mark(month, request_id, "completed")
            raise RuntimeError("Google returned incomplete timing marks; the track was not saved")
        starts = [marks[f"s{index}"] for index in range(first, first + count)]
        audio = base64.b64decode(response["audioContent"])
        name = f"narration-{key[:24]}-google-neural2-part-{part}.mp3"
        file_id, sha = tx.add_blob(audio, "Audio", name, "audio/mpeg")
        ledger.mark(month, request_id, "completed")
        tracks.append({"file_id": file_id, "sha256": sha, "startSentence": first, "sentenceStarts": starts})
    manifest = {"version": 2, "cacheKey": key, "provider": "Google Cloud Text-to-Speech", "voice": voice,
                "speakingRate": rate, "characterCount": characters, "sentenceCount": len(sentences),
                "passageHash": passage["passage_sha256"], "generatedAt": _now(), "tracks": tracks}
    manifest_id, _ = tx.add_blob(json.dumps(manifest).encode(), "Audio", f"narration-{key[:24]}-manifest.json",
                                 "application/json")
    values = {"topic_id": topic["id"], "passage_sha256": passage["passage_sha256"], "provider": "google-neural2",
              "voice": voice, "speaking_rate": rate, "manifest_file_id": manifest_id, "status": "ready",
              "characters": characters, "sentence_count": len(sentences), "timing": "provider-timepoints"}
    if existing:
        tx.update("audio_tracks", key, values)
    else:
        tx.insert("audio_tracks", {"id": key, **values})
    return {**estimate, "reused": False}
