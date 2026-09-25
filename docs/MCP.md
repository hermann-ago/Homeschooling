# Connecting a desktop AI tutor (MCP)

`tutor_mcp/bridge.py` is a stdio MCP server that uses only the Python standard library. It calls the home server over HTTP with a **tutor** credential. It never writes to Google Sheets directly and never sees Google credentials.

## 1. Pair the bridge (on the host computer, with the server running)

```powershell
backend\venv\Scripts\python launcher\homeschooling.py pair-agent --name "Codex"
```

This stores the tutor credential for the current Windows user, protected with DPAPI. A bridge on another computer can take the credential from the `HOMESCHOOLING_AGENT_TOKEN` environment variable instead.

## 2. Register the bridge

**Codex** (`%USERPROFILE%\.codex\config.toml`):

```toml
[mcp_servers.homeschooling]
command = "C:\\Users\\<you>\\source\\Homeschooling\\backend\\venv\\Scripts\\python.exe"
args = ["C:\\Users\\<you>\\source\\Homeschooling\\tutor_mcp\\bridge.py"]
env = { HOMESCHOOLING_URL = "http://127.0.0.1:8000" }
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{"mcpServers": {"homeschooling": {
  "command": "C:\\Users\\<you>\\source\\Homeschooling\\backend\\venv\\Scripts\\python.exe",
  "args": ["C:\\Users\\<you>\\source\\Homeschooling\\tutor_mcp\\bridge.py"],
  "env": {"HOMESCHOOLING_URL": "http://127.0.0.1:8000"}}}}
```

Set `HOMESCHOOLING_READER_BASE` to the LAN address (for example `http://192.168.1.20:8000`) if the reader links should open on another device.

## 3. Add the skill

Copy or link `tutor/skills/home-tutor` into the client's skills folder, and point the subject project at `tutor/subjects/<subject>/GUIDE.md`. The History project's new entry instructions are rendered by `python -m migration.cutover history-instructions` (see MIGRATION.md).

## Tools

| Tool | Purpose |
|---|---|
| `list_learners` | Learners and subjects |
| `lesson_context` | Phase `start`, `reading` or `closeout` context for the current topic. It includes an unfinished session's exact next prompt. |
| `start_lesson` | Starts, or resumes, a session. Returns `reader_url`, which the client opens and visually verifies. |
| `get_assignments`, `assign_questions` | Test questions mapped to the topic |
| `grading_context` | **Teacher-only** key entries and passage evidence for named questions |
| `record_attempts` | First answers verbatim, reading certainty, results, help, revisions and source notes |
| `save_checkpoint` | Unfinished observations plus the exact next prompt (append-only) |
| `update_reviews` | Specific review concepts, closed only after a later independent check |
| `attach_work` | Photo or PDF of handwritten work, saved to Drive `Student Work` |
| `finish_lesson` | Actual session summary and understanding, plus an explicit next topic. Closes the reader session. |
| `close_reader` | Closes the lesson's reader. The home server keeps running. |
| `review_passage` | Records a page-by-page review of an extracted passage |
| `narration` | Estimate (the default) or generate one narrator within the shared monthly guard |
| `save_preference` | A confirmed learner or parent preference |
| `sync_status` | Saved, pending or needs-reconciliation state |

Every mutation needs a stable `operation_id`, and session mutations also need the `expected_revision` from the previous response. Each result includes a receipt with `sync_state`. If a call times out, repeat it with the same `operation_id`. The server returns the original result and never creates a duplicate.
