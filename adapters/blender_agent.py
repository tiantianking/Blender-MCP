from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .task_context import build_task_request


def _toml_string(value: str) -> str:
    """Quote a value as a TOML basic string, escaping backslashes and quotes
    so Windows paths (or user names containing quotes) cannot break the
    inline `codex -c` configuration."""
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f"'{escaped}'"


class BlenderAgentAdapter:
    """Run a real Codex tool loop against the configured Blender MCP."""

    def __init__(self, project_root: str | Path, timeout: int = 900):
        self.project_root = Path(project_root).resolve()
        self.timeout = timeout
        self.uvx = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "AppData/Local/hermes/bin/uvx.exe"

    def execute(self, prompt: str, reference_image: str | None = None, stage: str = "single") -> dict:
        task_request = build_task_request(prompt, stage, reference_image)
        instruction = (
            "You are the Blender Agent embedded in the user's Blender Director panel. "
            "Carry out the USER_REQUEST in the currently open Blender project, not merely explain how. "
            "Use only the configured Blender MCP tools for task actions. Do not use shell commands, browser or computer UI, "
            "and do not read, edit or delete unrelated files. First call get_addon_status and get_scene_info. "
            "Never call bpy.ops.wm.read_factory_settings, read_homefile, open_mainfile, quit_blender, addon_disable, "
            "or unregister an add-on. Never reset Blender to clear a scene. If cleanup is required, selectively remove only "
            "objects or collections inside the task scope while preserving all MCP and Director services. "
            "Use asset-library tools when a suitable real asset exists; use structured previz tools where available; otherwise use execute_blender_code with bpy. "
            "Work in small verifiable steps. After modifications, call get_scene_info and get_viewport_screenshot to verify. "
            "Never claim success unless the requested scene change is visible or structurally verified. "
            "Do not overwrite the .blend file unless the user explicitly asks to save. "
            "Return a short Chinese result describing what was actually completed and any real limitation.\n\n"
            f"USER_REQUEST:\n{task_request}"
        )
        with tempfile.TemporaryDirectory(prefix="ai-previz-agent-") as temp_dir:
            output_file = Path(temp_dir) / "result.txt"
            python_exe = sys.executable
            companion_server = self.project_root / "companion_mcp" / "server.py"
            command = [
                "codex", "exec", "--ignore-user-config", "--approve-for-me", "--ephemeral",
                "--skip-git-repo-check", "--color", "never", "-C", str(self.project_root),
                "-c", f"mcp_servers.blender.command={_toml_string(self.uvx)}",
                "-c", "mcp_servers.blender.args=['mcp-for-blender']",
                "-c", f"mcp_servers.ai_previz.command={_toml_string(python_exe)}",
                "-c", f"mcp_servers.ai_previz.args=[{_toml_string(companion_server)}]",
                "--output-last-message", str(output_file), instruction,
            ]
            if reference_image:
                command[-1:-1] = ["-i", str(Path(reference_image).resolve())]
            completed = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=self.timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0:
                details = (completed.stderr or completed.stdout)[-1600:]
                raise RuntimeError(f"Blender Agent failed: {details}")
            if not output_file.exists():
                raise RuntimeError("Blender Agent returned no final result")
            message = output_file.read_text(encoding="utf-8", errors="replace").strip()
            return {"ok": True, "agent": True, "message": message or "Agent completed"}
