from __future__ import annotations

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))
from unittest.mock import MagicMock
if "bpy" not in sys.modules:
    sys.modules["bpy"] = MagicMock()
if "mathutils" not in sys.modules:
    sys.modules["mathutils"] = MagicMock()

from ai_previz_director.director.tasks import TaskManager, VALID_STAGES
from ai_previz_director.director.errors import ValidationError


def test_task_lifecycle():
    tm = TaskManager()
    task = tm.create_task(provider="polyhaven", task_id="task_test_01")
    assert task.task_id == "task_test_01"
    assert task.provider == "polyhaven"
    assert task.stage == "queued"
    assert task.progress_percent == "unknown"

    tm.update_task("task_test_01", stage="downloading", progress_percent=45.5)
    data = tm.get_task("task_test_01")["task"]
    assert data["stage"] == "downloading"
    assert data["progress_percent"] == 45.5
    assert data["elapsed_seconds"] >= 0.0

    tm.update_task("task_test_01", stage="importing", progress_percent="unknown")
    data2 = tm.get_task("task_test_01")["task"]
    assert data2["stage"] == "importing"
    assert data2["progress_percent"] == "unknown"

    tm.update_task("task_test_01", stage="succeeded", progress_percent=100.0)
    data3 = tm.get_task("task_test_01")["task"]
    assert data3["stage"] == "succeeded"
    assert data3["progress_percent"] == 100.0


def test_task_invalid_stage_rejected():
    tm = TaskManager()
    tm.create_task("rodin", "task_02")
    with pytest.raises(ValidationError, match="Invalid task stage"):
        tm.update_task("task_02", stage="magical_stage")


def test_task_retries():
    tm = TaskManager()
    tm.create_task("sketchfab", "task_03")
    tm.update_task(
        "task_03",
        stage="failed",
        retryable=True,
        error_type="NetworkTimeout",
        error_message="Connection timed out after 30s",
    )
    data = tm.get_task("task_03")["task"]
    assert data["stage"] == "failed"
    assert data["retryable"] is True
    assert data["retry_count"] == 1
    assert data["error_type"] == "NetworkTimeout"
