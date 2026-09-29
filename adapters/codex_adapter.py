from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from .base import IntentAdapter


class CodexAdapter(IntentAdapter):
    def __init__(self, project_root: str | Path, timeout: int = 120):
        self.project_root = Path(project_root).resolve()
        self.schema_path = self.project_root / "config" / "director_intent.schema.json"
        self.timeout = timeout

    def compile_intent(self, prompt: str, previz_context: dict, screenshot: str | None = None) -> dict:
        instruction = (
            "You are an intent compiler, not a Blender operator. Return only a JSON object matching the supplied schema. "
            "Never write Python, never call tools, and never modify files or Blender. Resolve targets only from PREVIZ_CONTEXT. "
            "Every operation field required by the response schema but unused by that operation must be null. "
            "speed_factor means playback speed: 0.7 means 70% speed. A right orbit is a negative angle around world Z. "
            "If a request cannot be represented by the schema, do not invent fields; choose the smallest safe supported operations.\n\n"
            f"USER_PROMPT:\n{prompt}\n\nPREVIZ_CONTEXT:\n{json.dumps(previz_context, ensure_ascii=False, separators=(',', ':'))}"
        )
        with tempfile.TemporaryDirectory(prefix="ai-previz-intent-") as temp_dir:
            output_file = Path(temp_dir) / "intent.json"
            command = [
                "codex", "exec", "--ignore-user-config", "--ephemeral", "--sandbox", "read-only",
                "--skip-git-repo-check", "--output-schema", str(self.schema_path),
                "--output-last-message", str(output_file), "--color", "never", "-C", str(self.project_root),
            ]
            if screenshot:
                command.extend(["-i", os.path.abspath(screenshot)])
            command.append(instruction)
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if completed.returncode != 0:
                raise RuntimeError(f"Codex intent compile failed: {(completed.stderr or completed.stdout)[-1200:]}")
            if not output_file.exists():
                raise RuntimeError("Codex did not produce a structured intent")
            try:
                intent = json.loads(output_file.read_text(encoding="utf-8"))
                intent["operations"] = [
                    {key: value for key, value in operation.items() if value is not None}
                    for operation in intent["operations"]
                ]
                return intent
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Codex returned invalid JSON: {output_file.read_text(encoding='utf-8')[:500]}") from exc

