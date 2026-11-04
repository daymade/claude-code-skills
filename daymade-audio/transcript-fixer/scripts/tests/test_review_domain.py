"""Domain admission and compare-and-swap metadata repair controls."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core.review_queue as module
from core.review_queue import ReviewQueue, ReviewQueueError


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "is_temp_path", lambda _: False)
    db = tmp_path / "queue.db"
    with sqlite3.connect(db) as conn:
        conn.executescript((Path(__file__).parents[1] / "core/schema.sql").read_text())
    return ReviewQueue(db), tmp_path / "course.md"


def item(path, original="甲词", **extra):
    return {"file": str(path), "original": original, **extra}


@pytest.mark.parametrize("missing", [{}, {"domain": ""}, {"domain": None}])
def test_classified_file_requires_explicit_domain(store, missing):
    queue, path = store
    queue.enqueue([item(path, domain="project-a")])
    with pytest.raises(ReviewQueueError, match="domain required"):
        queue.enqueue([item(path, "乙词", **missing)])
    assert len(queue.list_items(status=None)) == 1


def test_general_and_intentional_multi_domain_remain_usable(store):
    queue, path = store
    assert queue.enqueue([item(path)])["added"]
    assert queue.enqueue([item(path, "乙词", domain="project-a")])["added"]
    with pytest.raises(ReviewQueueError, match="domain conflict"):
        queue.enqueue([item(path, "丙词", domain="project-b")])
    assert queue.enqueue([item(path, "丙词", domain="project-b",
                               domain_reason="Explicitly classified second topic")])["added"]
    assert queue.enqueue([item(path, "丁词", domain="project-b")])["added"]
    assert queue.enqueue([item(path, "戊词", domain="general",
                               domain_reason="Explicitly unclassified passage")])["added"]


def test_domain_failure_rolls_back_the_entire_batch(store):
    queue, path = store
    queue.enqueue([item(path, domain="project-a")])
    with pytest.raises(ReviewQueueError):
        queue.enqueue([item(path, "乙词", domain="project-a"), item(path, "丙词")])
    assert len(queue.list_items(status=None)) == 1


def repair(queue, path, ids, **kwargs):
    return queue.repair_domain(ids, file_path=str(path), from_domain="general",
                               to_domain="project-a", reason="Correct omitted project binding",
                               by="fixture-operator", **kwargs)


def test_repair_preview_then_apply_preserves_every_other_column(store):
    queue, path = store
    ids = queue.enqueue([item(path), item(path, "乙词")])["added"]
    before = [queue.get(i).to_dict() for i in ids]
    assert repair(queue, path, ids)["applied"] is False
    assert [queue.get(i).to_dict() for i in ids] == before
    assert repair(queue, path, ids, apply=True)["applied"] is True
    for previous, i in zip(before, ids):
        previous["domain"] = "project-a"
        assert queue.get(i).to_dict() == previous
    with sqlite3.connect(queue.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='review_domain_repair'").fetchone()[0] == 2
    with pytest.raises(ReviewQueueError):
        repair(queue, path, ids, apply=True)


@pytest.mark.parametrize("fault", ["missing", "wrong_file", "decided", "linked"])
def test_repair_refuses_bad_batch_without_partial_writes(store, fault):
    queue, path = store
    ids = queue.enqueue([item(path), item(path, "乙词")])["added"]
    with sqlite3.connect(queue.db_path) as conn:
        if fault == "wrong_file":
            conn.execute("UPDATE review_items SET file_path=? WHERE id=?", (str(path)+"other", ids[1]))
        elif fault == "decided":
            conn.execute("UPDATE review_items SET status='kept_original' WHERE id=?", (ids[1],))
        elif fault == "linked":
            conn.execute("UPDATE review_items SET occurrence_parent=? WHERE id=?", (ids[0], ids[1]))
    if fault == "missing":
        ids.append(999999)
    with pytest.raises(ReviewQueueError):
        repair(queue, path, ids, apply=True)
    assert queue.get(ids[0]).domain == "general"
    with sqlite3.connect(queue.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='review_domain_repair'").fetchone()[0] == 0


def test_official_cli_preview_and_apply(store, tmp_path):
    queue, path = store
    ids = queue.enqueue([item(path)])["added"]
    plan = tmp_path / "repair.json"
    plan.write_text(json.dumps({"ids": ids, "file": str(path), "from_domain": "general",
                                "to_domain": "project-a", "reason": "Fix project metadata", "by": "fixture"}))
    script = Path(__file__).resolve().parents[1] / "review_domain.py"
    cmd = [sys.executable, str(script), "--db", str(queue.db_path), "--plan", str(plan)]
    preview = subprocess.run(cmd, text=True, capture_output=True)
    assert preview.returncode == 0, preview.stderr
    assert json.loads(preview.stdout)["applied"] is False
    applied = subprocess.run(cmd + ["--apply"], text=True, capture_output=True)
    assert applied.returncode == 0, applied.stderr
    assert queue.get(ids[0]).domain == "project-a"
