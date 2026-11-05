import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("HOMESCHOOLING_SKIP_APP", "1")
# Tests must never read or write the real data folder (database, narration ledger).
os.environ["HOMESCHOOLING_DATA"] = str(Path(__file__).resolve().parent / ".tmp-data")


@pytest.fixture(autouse=True)
def isolated_drive_detection(monkeypatch):
    # Test hosts must not probe the family's real synced folder.
    monkeypatch.setattr("config.DRIVE_FOLDER_CANDIDATES", ())
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("INWORLD_API_KEY", raising=False)


class Harness:
    def __init__(self, tmp_path):
        from fastapi.testclient import TestClient

        from app_context import AppContext
        from config import HostConfig
        from main import create_app
        self.drive = tmp_path / "Drive" / "Homeschooling"
        self.drive.mkdir(parents=True)
        self.config = HostConfig(tmp_path / "host")
        self.config.update(drive_folder=str(self.drive))
        # Tests opt in to background next-lesson preparation (tests/test_prepare_next.py).
        self.config.update(preparation={'auto_next': False})
        self.ctx = AppContext(self.config, start_worker=False)
        self.app = create_app(self.ctx)
        self.client = TestClient(self.app)
        self.tokens = {"tutor": self.ctx.devices.issue("test tutor", "tutor")}

    def add_file(self, data: bytes, relative: str) -> str:
        """Put a file into the test Drive folder, as Drive for desktop would."""
        path = self.drive / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return relative

    def headers(self, role="family", key=None):
        """Family devices send no credential; only the tutor's bridge does."""
        headers = {"Authorization": f"Bearer {self.tokens[role]}"} if role == "tutor" else {}
        if key:
            headers["Idempotency-Key"] = key
        return headers

    def call(self, method, path, role="family", key=None, **kwargs):
        return self.client.request(method, path, headers=self.headers(role, key), **kwargs)

    def restart(self):
        """Simulate a server restart with the same database and Drive folder."""
        from app_context import AppContext
        from main import create_app
        from fastapi.testclient import TestClient
        self.ctx = AppContext(self.config, start_worker=False)
        self.app = create_app(self.ctx)
        self.client = TestClient(self.app)


@pytest.fixture
def harness(tmp_path):
    return Harness(tmp_path)
