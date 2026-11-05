"""Backups of both databases are pruned, each to its own count."""
from storage import backups


def test_ai_usage_backups_are_pruned_like_family_backups(tmp_path):
    for i in range(backups.KEEP_BACKUPS + 5):
        (tmp_path / f"homeschooling-2026{i:04d}T000000Z.sqlite3").write_text("x")
        (tmp_path / f"ai-usage-2026{i:04d}T000000Z.sqlite3").write_text("x")
    (tmp_path / "ai-usage-20260000T000000Z.sqlite3-journal").write_text("x")
    (tmp_path / "before-cleanup.sqlite3").write_text("kept")
    backups.prune(tmp_path)
    assert len(list(tmp_path.glob("homeschooling-*.sqlite3"))) == backups.KEEP_BACKUPS
    assert len(list(tmp_path.glob("ai-usage-*.sqlite3"))) == backups.KEEP_USAGE_BACKUPS
    assert not (tmp_path / "ai-usage-20260000T000000Z.sqlite3").exists()
    assert not (tmp_path / "ai-usage-20260000T000000Z.sqlite3-journal").exists()
    newest = backups.KEEP_BACKUPS + 4
    assert (tmp_path / f"ai-usage-2026{newest:04d}T000000Z.sqlite3").exists()
    assert not (tmp_path / f"ai-usage-2026{newest - backups.KEEP_USAGE_BACKUPS:04d}T000000Z.sqlite3").exists()
    assert (tmp_path / "before-cleanup.sqlite3").exists()
