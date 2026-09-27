"""Homeschooling tutor MCP bridge (stdio, standard library only).

Desktop AI clients (Codex, Claude Desktop, …) start this script and talk MCP
over stdin/stdout. Every tool calls the home server's HTTP API with a
tutor-role device credential; the bridge never opens the database or the
Drive folder itself and never sees any Google credential.

Configuration (environment variables):
  HOMESCHOOLING_URL          home server address (default http://127.0.0.1:8000)
  HOMESCHOOLING_READER_BASE  address used in reader links (default: HOMESCHOOLING_URL)
  HOMESCHOOLING_AGENT_TOKEN  tutor credential; otherwise the DPAPI-protected file
                             written by ``launcher/homeschooling.py pair-agent``
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

VERSION = "1.0.0"
PROTOCOL = "2025-06-18"


# ── credentials ──────────────────────────────────────────────────────────────

def _data_dir() -> Path:
    """The project's ``data`` folder, next to this bridge's folder (as in backend/config.py)."""
    if os.getenv("HOMESCHOOLING_DATA"):
        return Path(os.environ["HOMESCHOOLING_DATA"])
    return Path(__file__).resolve().parents[1] / "data"


def _unprotect(payload: bytes) -> bytes:
    marker, body = payload[:6], payload[6:]
    if marker == b"PLAIN1":
        return body
    if marker != b"DPAPI1" or sys.platform != "win32":
        raise RuntimeError("The stored tutor credential cannot be read on this computer")
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(value):
        buffer = ctypes.create_string_buffer(value, len(value))
        return Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))

    source, entropy, result = blob(body), blob(b"Homeschooling home server v1"), Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                                                    0x01, ctypes.byref(result)):
        raise RuntimeError("Windows could not unlock the tutor credential")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)


def agent_token() -> str:
    token = os.getenv("HOMESCHOOLING_AGENT_TOKEN")
    if token:
        return token
    path = _data_dir() / "secrets" / "agent-token.bin"
    if not path.exists():
        raise RuntimeError("No tutor credential. On the host run: python launcher/homeschooling.py pair-agent")
    return _unprotect(path.read_bytes()).decode()


# ── HTTP ─────────────────────────────────────────────────────────────────────

class HomeServer:
    def __init__(self, base_url: str | None = None, token: str | None = None, transport=None):
        self.base = (base_url or os.getenv("HOMESCHOOLING_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.reader_base = (os.getenv("HOMESCHOOLING_READER_BASE") or self.base).rstrip("/")
        self._token = token
        self.transport = transport or self._urllib

    @property
    def token(self) -> str:
        if self._token is None:
            self._token = agent_token()
        return self._token

    def _urllib(self, method, path, headers, body):
        request = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def call(self, method: str, path: str, *, query: dict | None = None, json_body=None, key: str | None = None,
             multipart: tuple | None = None) -> dict:
        if query:
            path += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        body = None
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(json_body).encode()
        if multipart is not None:
            boundary = uuid.uuid4().hex
            fields, (field, filename, data, mime) = multipart
            parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                     for k, v in fields.items() if v is not None]
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
                         f"Content-Type: {mime}\r\n\r\n".encode() + data + b"\r\n")
            body = b"".join(parts) + f"--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        if key:
            headers["Idempotency-Key"] = key
        attempts = 3 if key or method == "GET" else 1
        for attempt in range(attempts):
            try:
                status, response_headers, raw = self.transport(method, path, headers, body)
                break
            except (urllib.error.URLError, OSError, TimeoutError) as error:
                if attempt == attempts - 1:
                    raise RuntimeError(f"The home server did not answer ({error}). If this was a save, call the "
                                       "same tool again with the same operation_id; it will not duplicate.") from error
                time.sleep(1 + attempt)
        lowered = {k.lower(): v for k, v in response_headers.items()}
        payload = json.loads(raw) if raw else {}
        if status >= 400:
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
            raise ToolError(status, detail)
        if key:
            return {"result": payload, "receipt": {
                "operation_id": key, "sync_state": lowered.get("x-sync-state", "saved"),
                "replayed": lowered.get("x-idempotent-replay") == "true",
                "meaning": {"saved": "committed to the Homeschooling database on the home server"
                            }.get(lowered.get("x-sync-state", "saved"), "not saved; check the error")}}
        return payload


class ToolError(Exception):
    def __init__(self, status, detail):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


# ── tools ────────────────────────────────────────────────────────────────────

def _schema(properties: dict, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


INT = {"type": "integer"}
STR = {"type": "string"}
OPERATION = {"type": "string", "description": "Stable ID for this save (reuse it when retrying the same save)",
             "pattern": "^[A-Za-z0-9_.:-]{8,120}$"}
REVISION = {"type": "integer", "description": "Session revision from the last response (optimistic concurrency)"}
MUTATION = ("operation_id",)

TOOLS = {
    "list_learners": ("List learners and their subjects.", _schema({}), None),
    "lesson_context": ("Phase-specific lesson context. phase=start|reading|closeout. Use grading_context for keys.",
                       _schema({"child_id": INT, "subject_id": INT, "phase": {"type": "string",
                                "enum": ["start", "reading", "closeout"]}}, ("child_id", "subject_id")), None),
    "start_lesson": ("Start or resume today's lesson (an unfinished session is always resumed first). Returns the "
                     "reader URL to open and visually verify before handing off.",
                     _schema({"child_id": INT, "subject_id": INT, "topic_id": INT, "operation_id": OPERATION},
                             ("child_id", "subject_id", "operation_id")), None),
    "get_assignments": ("Test questions mapped to the current topic (learner-safe numbers and pages).",
                        _schema({"session_id": STR}, ("session_id",)), None),
    "assign_questions": ("Record which handwritten questions were assigned.",
                         _schema({"session_id": STR, "expected_revision": REVISION,
                                  "questions": {"type": "array", "items": INT}, "note": STR,
                                  "operation_id": OPERATION}, ("session_id", "expected_revision", "questions",
                                                               "operation_id")), None),
    "grading_context": ("TEACHER-ONLY key entries and passage evidence for named questions. Never show to the "
                        "learner before an attempt.",
                        _schema({"child_id": INT, "subject_id": INT, "questions": {"type": "array", "items": INT}},
                                ("child_id", "subject_id", "questions")), None),
    "record_attempts": ("Record original answers, reading certainty, results, help, revisions and source notes. "
                        "First answers are immutable; assisted work is never independent.",
                        _schema({"session_id": STR, "expected_revision": REVISION,
                                 "attempts": {"type": "array", "items": {"type": "object"}},
                                 "operation_id": OPERATION},
                                ("session_id", "expected_revision", "attempts", "operation_id")), None),
    "save_checkpoint": ("Save unfinished observations and the exact next prompt at a meaningful pause.",
                        _schema({"session_id": STR, "expected_revision": REVISION, "phase": STR,
                                 "next_prompt": STR, "observations": {"type": "array", "items": {"type": "object"}},
                                 "minutes": INT, "operation_id": OPERATION},
                                ("session_id", "expected_revision", "phase", "next_prompt", "observations",
                                 "operation_id")), None),
    "update_reviews": ("Add or update specific review concepts. Close only after a later independent check.",
                       _schema({"session_id": STR, "expected_revision": REVISION,
                                "reviews": {"type": "array", "items": {"type": "object"}}, "operation_id": OPERATION},
                               ("session_id", "expected_revision", "reviews", "operation_id")), None),
    "attach_work": ("Upload a photo/PDF of handwritten work from a local file path to Drive Student Work.",
                    _schema({"session_id": STR, "expected_revision": REVISION, "file_path": STR, "note": STR,
                             "operation_id": OPERATION},
                            ("session_id", "expected_revision", "file_path", "operation_id")), None),
    "finish_lesson": ("Finish after actual completion: what the learner explained, difficulty, help, "
                      "understanding, explicit next_topic_id; closes the reader (not the home server).",
                      _schema({"session_id": STR, "expected_revision": REVISION, "next_topic_id": INT,
                               "learner_explained": STR, "difficulty": STR, "help_that_worked": STR,
                               "next_action": STR, "parent_observation": STR, "understanding": {
                                   "type": "string", "enum": ["Independent", "With help", "Needs help", "Not assessed"]},
                               "next_step": STR, "complete_topic": {"type": "boolean"}, "minutes": INT,
                               "session_type": STR, "chapter_updates": {"type": "array", "items": {"type": "object"}},
                               "operation_id": OPERATION},
                              ("session_id", "expected_revision", "next_topic_id", "learner_explained",
                               "operation_id")), None),
    "close_reader": ("Close this lesson's reader session. The home server keeps running.",
                     _schema({"session_id": STR}, ("session_id",)), None),
    "review_passage": ("Record that every assigned PDF page was inspected; supply corrected passage text or the "
                       "unchanged draft's passage_sha256.",
                       _schema({"topic_id": INT, "reviewed_pdf_pages": {"type": "array", "items": INT},
                                "notes": STR, "passage": STR, "passage_sha256": STR, "operation_id": OPERATION},
                               ("topic_id", "reviewed_pdf_pages", "notes", "operation_id")), None),
    "narration": ("Estimate (dry_run true, default) or generate one narrator for the lesson's passage; a voice already "
                  "built for the same text (for example from the app's reader) is reused. Respects the shared "
                  "150,000-character monthly guard; overage needs a parent.",
                  _schema({"topic_id": INT, "dry_run": {"type": "boolean"}, "voice": STR,
                           "operation_id": OPERATION}, ("topic_id", "operation_id")), None),
    "save_preference": ("Save a preference the learner or parent confirmed (e.g. narrator).",
                        _schema({"child_id": INT, "key": STR, "value": {}, "confirmed_by": STR,
                                 "operation_id": OPERATION}, ("child_id", "key", "value", "confirmed_by",
                                                              "operation_id")), None),
    "storage_status": ("Whether the database and the synced Drive folder (books, audio) are available.",
                       _schema({}), None),
}


def run_tool(server: HomeServer, name: str, args: dict):
    op = args.get("operation_id")
    body = {k: v for k, v in args.items() if k not in ("operation_id", "session_id", "topic_id")}
    if name == "list_learners":
        return server.call("GET", "/api/tutor/learners")
    if name == "lesson_context":
        return server.call("GET", "/api/tutor/context", query={"child_id": args["child_id"],
                                                               "subject_id": args["subject_id"],
                                                               "phase": args.get("phase", "start")})
    if name == "grading_context":
        return server.call("GET", "/api/tutor/context", query={
            "child_id": args["child_id"], "subject_id": args["subject_id"], "phase": "grading",
            "questions": ",".join(str(q) for q in args["questions"])})
    if name == "start_lesson":
        response = server.call("POST", "/api/tutor/sessions/start", key=op, json_body={
            "child_id": args["child_id"], "subject_id": args["subject_id"], "topic_id": args.get("topic_id")})
        response["result"]["reader_url"] = server.reader_base + response["result"]["reader_path"]
        response["result"]["next"] = ("Open reader_url and visually verify the title, start/stop boundaries, "
                                      "illustrations and narration highlighting before telling the learner it is "
                                      "ready. An open reader is not evidence of reading.")
        return response
    session = args.get("session_id")
    if name == "get_assignments":
        return server.call("GET", f"/api/tutor/sessions/{session}/assignments")
    if name == "assign_questions":
        return server.call("POST", f"/api/tutor/sessions/{session}/assignments", key=op, json_body=body)
    if name == "record_attempts":
        return server.call("POST", f"/api/tutor/sessions/{session}/attempts", key=op, json_body=body)
    if name == "save_checkpoint":
        return server.call("POST", f"/api/tutor/sessions/{session}/checkpoint", key=op, json_body=body)
    if name == "update_reviews":
        return server.call("POST", f"/api/tutor/sessions/{session}/reviews", key=op, json_body=body)
    if name == "attach_work":
        path = Path(args["file_path"]).expanduser()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return server.call("POST", f"/api/tutor/sessions/{session}/evidence", key=op, multipart=(
            {"expected_revision": args["expected_revision"], "note": args.get("note")},
            ("file", path.name, path.read_bytes(), mime)))
    if name == "finish_lesson":
        return server.call("POST", f"/api/tutor/sessions/{session}/finish", key=op, json_body=body)
    if name == "close_reader":
        return server.call("POST", f"/api/tutor/sessions/{session}/reader/close")
    if name == "review_passage":
        return server.call("POST", f"/api/tutor/passages/{args['topic_id']}/review", key=op, json_body=body)
    if name == "narration":
        return server.call("POST", "/api/tutor/audio/generate", key=op, json_body={
            "topic_id": args["topic_id"], "dry_run": args.get("dry_run", True), "voice": args.get("voice")})
    if name == "save_preference":
        return server.call("POST", "/api/tutor/preferences", key=op, json_body=body)
    if name == "storage_status":
        return server.call("GET", "/api/storage/status")
    raise KeyError(name)


# ── MCP stdio protocol ───────────────────────────────────────────────────────

class Bridge:
    def __init__(self, server: HomeServer | None = None):
        self.server = server or HomeServer()

    def handle(self, message: dict) -> dict | None:
        method = message.get("method")
        request_id = message.get("id")
        if request_id is None:
            return None  # notifications (initialized, cancelled) need no reply
        try:
            if method == "initialize":
                requested = (message.get("params") or {}).get("protocolVersion") or PROTOCOL
                result = {"protocolVersion": requested, "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "homeschooling-tutor", "version": VERSION},
                          "instructions": "Use with the home-tutor skill. The conversation is the classroom; "
                                          "these tools read context and save evidence through the home server."}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [{"name": name, "description": description, "inputSchema": schema}
                                    for name, (description, schema, _) in TOOLS.items()]}
            elif method == "tools/call":
                params = message.get("params") or {}
                name = params.get("name")
                if name not in TOOLS:
                    return _error(request_id, -32602, f"Unknown tool {name}")
                arguments = params.get("arguments") or {}
                missing = [k for k in TOOLS[name][1]["required"] if k not in arguments]
                if missing:
                    result = _tool_result({"error": f"Missing {', '.join(missing)}"}, True)
                else:
                    try:
                        result = _tool_result(run_tool(self.server, name, arguments), False)
                    except ToolError as error:
                        result = _tool_result({"error": error.detail, "status": error.status}, True)
                    except (RuntimeError, OSError) as error:
                        result = _tool_result({"error": str(error)}, True)
            else:
                return _error(request_id, -32601, f"Method not found: {method}")
        except Exception as error:  # pragma: no cover - last-resort protocol safety
            return _error(request_id, -32603, str(error))
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def serve(self, stdin=sys.stdin, stdout=sys.stdout):
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                stdout.write(json.dumps(_error(None, -32700, "Parse error")) + "\n")
                stdout.flush()
                continue
            response = self.handle(message)
            if response is not None:
                stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                stdout.flush()


def _tool_result(payload, is_error: bool) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}],
            "structuredContent": payload if isinstance(payload, dict) else {"items": payload}, "isError": is_error}


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


if __name__ == "__main__":
    # MCP messages are UTF-8; Windows otherwise reads and writes pipes in the locale code page.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    Bridge().serve()
