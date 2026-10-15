from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, asdict

from .errors import ValidationError

VALID_STAGES = {
    "queued",
    "downloading",
    "importing",
    "verifying",
    "succeeded",
    "failed",
    "cancelled",
}


@dataclass
class PrevizTask:
    task_id: str
    provider: str
    stage: str
    created_at: float
    updated_at: float
    progress_percent: float | str = "unknown"
    retryable: bool = False
    retry_count: int = 0
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        now = time.time()
        elapsed = round(now - self.created_at, 2)
        data = asdict(self)
        data["elapsed_seconds"] = elapsed
        return data


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, PrevizTask] = {}

    def create_task(self, provider: str, task_id: str | None = None) -> PrevizTask:
        tid = task_id or f"task_{uuid.uuid4().hex[:12]}"
        now = time.time()
        task = PrevizTask(
            task_id=tid,
            provider=provider,
            stage="queued",
            created_at=now,
            updated_at=now,
            progress_percent="unknown",
            retryable=False,
            retry_count=0,
        )
        self._tasks[tid] = task
        return task

    def update_task(
        self,
        task_id: str,
        stage: str,
        progress_percent: float | str | None = None,
        retryable: bool | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> PrevizTask:
        task = self._tasks.get(task_id)
        if not task:
            raise ValidationError(f"Task not found: '{task_id}'")

        if stage not in VALID_STAGES:
            raise ValidationError(f"Invalid task stage '{stage}'. Must be one of: {sorted(VALID_STAGES)}")

        task.stage = stage
        task.updated_at = time.time()

        if progress_percent is not None:
            if isinstance(progress_percent, (int, float)):
                task.progress_percent = round(float(progress_percent), 2)
            else:
                task.progress_percent = "unknown"

        if retryable is not None:
            task.retryable = bool(retryable)

        if error_type is not None:
            task.error_type = error_type
        if error_message is not None:
            task.error_message = error_message

        if stage == "failed" and task.retryable:
            task.retry_count += 1

        return task

    def get_task(self, task_id: str) -> dict:
        task = self._tasks.get(task_id)
        if not task:
            raise ValidationError(f"Task not found: '{task_id}'")
        return {"ok": True, "task": task.to_dict()}


TASKS = TaskManager()
