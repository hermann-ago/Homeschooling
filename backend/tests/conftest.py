import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("HOMESCHOOLING_SKIP_APP", "1")
# Tests must never read or write the real narration ledger.
os.environ["LOCALAPPDATA"] = str(Path(__file__).resolve().parent / ".tmp-localappdata")


class Harness:
    def __init__(self, tmp_path):
        from fastapi.testclient import TestClient

        from app_context import AppContext
        from config import HostConfig
        from main import create_app
        from storage import FakeDrive, FakeSheets
        from storage.workbook import bootstrap

        self.sheets = FakeSheets()
        bootstrap(self.sheets)
        self.drive = FakeDrive()
        self.config = HostConfig(tmp_path / "host")
        self.ctx = AppContext(self.config, sheets=self.sheets, drive=self.drive, start_worker=False)
        self.app = create_app(self.ctx)
        self.client = TestClient(self.app)
        self.tokens = {role: self.ctx.devices.issue(f"test {role}", role) for role in ("parent", "learner", "tutor")}

    def headers(self, role="parent", key=None):
        headers = {"Authorization": f"Bearer {self.tokens[role]}"}
        if key:
            headers["Idempotency-Key"] = key
        return headers

    def call(self, method, path, role="parent", key=None, **kwargs):
        return self.client.request(method, path, headers=self.headers(role, key), **kwargs)

    def restart(self):
        """Simulate a server restart with the same local data and workbook."""
        from app_context import AppContext
        from main import create_app
        from fastapi.testclient import TestClient
        self.ctx = AppContext(self.config, sheets=self.sheets, drive=self.drive, start_worker=False)
        self.app = create_app(self.ctx)
        self.client = TestClient(self.app)


@pytest.fixture
def harness(tmp_path):
    return Harness(tmp_path)
