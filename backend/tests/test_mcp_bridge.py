import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tutor_mcp"))

from bridge import Bridge, HomeServer  # noqa: E402
from tests.test_tutoring import seed_history  # noqa: E402


def make_bridge(harness):
    def transport(method, path, headers, body):
        response = harness.client.request(method, path, headers=headers, content=body)
        return response.status_code, dict(response.headers), response.content
    server = HomeServer("http://192.168.1.2:8000", token=harness.tokens["tutor"], transport=transport)
    return Bridge(server)


def call(bridge, name, arguments, request_id=1):
    reply = bridge.handle({"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                           "params": {"name": name, "arguments": arguments}})
    return reply["result"]["isError"], json.loads(reply["result"]["content"][0]["text"])


def test_protocol_handshake_and_tool_list(harness):
    bridge = make_bridge(harness)
    init = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18", "capabilities": {}}})
    assert init["result"]["serverInfo"]["name"] == "homeschooling-tutor"
    assert bridge.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    names = {t["name"] for t in bridge.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
    assert {"start_lesson", "record_attempts", "save_checkpoint", "finish_lesson", "grading_context"} <= names
    assert bridge.handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})["error"]["code"] == -32601


def test_start_lesson_via_bridge_returns_reader_url_and_receipt(harness):
    s = seed_history(harness)
    bridge = make_bridge(harness)
    error, body = call(bridge, "start_lesson", {"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"],
                                                "operation_id": "codex-start-0001"})
    assert not error, body
    assert body["result"]["reader_url"].startswith("http://192.168.1.2:8000/lesson?learner=")
    assert body["result"]["next_prompt"] == "What did the man who spoke up do next?"
    assert body["receipt"] == {"operation_id": "codex-start-0001", "sync_state": "saved", "replayed": False,
                               "meaning": "committed to the Homeschooling database on the home server"}
    error, again = call(bridge, "start_lesson", {"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"],
                                                 "operation_id": "codex-start-0001"})
    assert again["receipt"]["replayed"] is True and again["result"] == body["result"]


def test_bridge_reports_conflicts_and_missing_fields_as_tool_errors(harness):
    s = seed_history(harness)
    bridge = make_bridge(harness)
    _, started = call(bridge, "start_lesson", {"child_id": s["lucas"]["id"], "subject_id": s["history"]["id"],
                                               "operation_id": "codex-start-0002"})
    error, body = call(bridge, "save_checkpoint", {"session_id": started["result"]["session_id"],
                                                   "expected_revision": 0, "phase": "discussion",
                                                   "next_prompt": "x", "observations": [],
                                                   "operation_id": "codex-cp-00001"})
    assert error and body["status"] == 409
    error, body = call(bridge, "finish_lesson", {"session_id": "x"})
    assert error and "Missing" in body["error"]
