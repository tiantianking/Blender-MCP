from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

APP_DIR = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "AI-Previz-Director"
RUNTIME_PATH = APP_DIR / "runtime.json"
ROOT = Path(__file__).resolve().parents[1]
mcp = FastMCP("AI Previz Director")


def _runtime() -> dict:
    if not RUNTIME_PATH.exists():
        raise RuntimeError("AI Previz Bridge runtime configuration is missing. Start the bridge first.")
    return json.loads(RUNTIME_PATH.read_text(encoding="utf-8-sig"))


def _ensure_bridge() -> None:
    port = 8765
    if RUNTIME_PATH.exists():
        try:
            port = int(_runtime().get("port", port))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
            return
    except Exception:
        pass
    if os.name == "nt":
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            raise RuntimeError("PowerShell was not found; cannot start the AI Previz Bridge")
        subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "start_bridge.ps1")],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        process = subprocess.Popen(
            [sys.executable, "-m", "bridge.server", "--port", str(port)],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        APP_DIR.mkdir(parents=True, exist_ok=True)
        (APP_DIR / "bridge.pid").write_text(str(process.pid), encoding="ascii")
    for _ in range(20):
        time.sleep(0.1)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                return
        except Exception:
            pass
    raise RuntimeError("AI Previz Bridge did not start")


def _call(method: str, payload: dict) -> dict:
    cfg = _runtime()
    data = json.dumps({"method": method, "payload": payload}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{cfg['port']}/director", data=data, method="POST",
        headers={"Content-Type": "application/json", "X-AI-Previz-Token": cfg["token"]},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"AI Previz Bridge call failed: {exc}") from exc


def _intent(operation: dict, prompt: str = "MCP structured operation") -> dict:
    return _call("execute_intent", {"intent": {"intent_version": 1, "operations": [operation]}, "prompt": prompt})


@mcp.tool()
def previz_get_state() -> dict:
    """Return compact semantic previz state, including all tagged actors, products, cameras and shots."""
    return _call("get_state", {})


@mcp.tool()
def previz_find_entity(reference: str) -> dict:
    """Resolve a semantic id, object name or alias without modifying Blender."""
    return _call("find_entity", {"reference": reference})


@mcp.tool()
def previz_tag_entity(reference: str, role: str, entity_id: str, aliases: list[str] | None = None) -> dict:
    """Persist a semantic role, stable id and aliases on a Blender object."""
    return _call("tag_entity", {"reference": reference, "role": role, "entity_id": entity_id, "aliases": aliases or []})


@mcp.tool()
def camera_set_lens(lens_mm: float, camera: str = "current_camera", subject: str | None = None, preserve_subject_framing: bool = False) -> dict:
    """Set camera focal length; optionally preserve a subject's framing by adjusting distance."""
    op = {"type": "camera_set_lens", "target": camera, "lens_mm": lens_mm, "preserve_subject_framing": preserve_subject_framing}
    if subject:
        op["subject"] = subject
    return _intent(op)


@mcp.tool()
def camera_dolly(distance: float, camera: str = "current_camera") -> dict:
    """Move a camera along its viewing direction. Positive values move toward the subject."""
    return _intent({"type": "camera_dolly", "target": camera, "distance": distance})


@mcp.tool()
def camera_orbit(subject: str, angle_degrees: float, camera: str = "current_camera") -> dict:
    """Reposition a camera around a subject on world Z and keep looking at it."""
    return _intent({"type": "camera_orbit", "target": camera, "subject": subject, "angle_degrees": angle_degrees})


@mcp.tool()
def camera_frame_subject(subject: str, camera: str = "current_camera", padding: float = 0.15) -> dict:
    """Frame the complete world-space bounds of a subject."""
    return _intent({"type": "camera_frame_subject", "target": camera, "subject": subject, "padding": padding})


@mcp.tool()
def actor_retime(actor: str, speed_factor: float, frame_start: int | None = None, frame_end: int | None = None) -> dict:
    """Retime a supported non-shared Action. 0.7 means 70 percent playback speed."""
    op = {"type": "actor_retime", "target": actor, "speed_factor": speed_factor}
    if frame_start is not None:
        op["frame_start"] = frame_start
    if frame_end is not None:
        op["frame_end"] = frame_end
    return _intent(op)


@mcp.tool()
def shot_product_closeup(product: str, shot: str = "last", hold_frames: int | None = None) -> dict:
    """Reframe the active camera on a tagged product and update shot metadata."""
    op = {"type": "shot_product_closeup", "target": product, "shot": shot}
    if hold_frames:
        op["hold_frames"] = hold_frames
    return _intent(op)


@mcp.tool()
def previz_undo() -> dict:
    """Undo the last committed Director transaction using its captured state."""
    return _intent({"type": "previz_undo"})


@mcp.tool()
def previz_redo() -> dict:
    """Redo the last undone Director transaction."""
    return _intent({"type": "previz_redo"})


@mcp.tool()
def previz_capture_view(output_path: str) -> dict:
    """Render a clean camera still without Blender UI overlays."""
    return _call("capture_view", {"output_path": output_path})


@mcp.tool()
def previz_export_clean(output_path: str, frame_start: int | None = None, frame_end: int | None = None) -> dict:
    """Render a clean camera-view MP4 for downstream video reference."""
    payload = {"output_path": output_path}
    if frame_start is not None:
        payload["frame_start"] = frame_start
    if frame_end is not None:
        payload["frame_end"] = frame_end
    return _call("export_clean", payload)


def main():
    _ensure_bridge()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

