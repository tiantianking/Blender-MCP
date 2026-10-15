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
def previz_get_state(detail_ids: list[str] | None = None) -> dict:
    """Return compact semantic previz state, including all tagged actors, products, cameras and shots."""
    return _call("get_state", {"detail_ids": detail_ids or []})


@mcp.tool()
def previz_set_frame(frame: int) -> dict:
    """Set the current frame and return the resulting semantic state, including the active shot camera."""
    return _call("set_frame", {"frame": frame})


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
def camera_follow(subject: str, camera: str = "current_camera", offset_x: float = 0.0, offset_y: float = -6.0, offset_z: float = 3.0) -> dict:
    """Attach a deterministic follow and look-at rig to a camera using a world-space offset."""
    return _intent({
        "type": "camera_follow", "target": camera, "subject": subject,
        "offset_x": offset_x, "offset_y": offset_y, "offset_z": offset_z,
    })


@mcp.tool()
def material_set_color(target: str, red: float, green: float, blue: float) -> dict:
    """Set the render material color of a semantic object and its mesh children using RGB values from 0 to 1."""
    return _intent({"type": "material_set_color", "target": target, "red": red, "green": green, "blue": blue})


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
def shot_create(shot_id: str, frame_start: int, frame_end: int, camera: str = "current_camera", subject: str | None = None, shot_type: str | None = None) -> dict:
    """Create a shot range and bind its start marker to a camera for automatic timeline switching."""
    op = {"type": "shot_create", "shot_id": shot_id, "frame_start": frame_start, "frame_end": frame_end, "target": camera}
    if subject:
        op["subject"] = subject
    if shot_type:
        op["shot_type"] = shot_type
    return _intent(op)


@mcp.tool()
def shot_set_camera(shot: str, camera: str) -> dict:
    """Assign a different camera to a shot and its timeline marker."""
    return _intent({"type": "shot_set_camera", "shot": shot, "target": camera})


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


@mcp.tool()
def previz_get_scene_graph(
    cursor: str | None = None,
    limit: int = 200,
    collection: str | None = None,
    include_hidden: bool = True,
    include_materials: bool = False,
) -> dict:
    """Query complete scene tree with pagination, hierarchy (parent/children), collections, world transform, AABB bounds and semantic tags."""
    return _call("get_scene_graph", {
        "cursor": cursor,
        "limit": limit,
        "collection": collection,
        "include_hidden": include_hidden,
        "include_materials": include_materials,
    })


@mcp.tool()
def previz_set_object_transform(
    reference: str,
    location: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
    mode: str = "absolute",
    space: str = "world",
    keyframe: bool = False,
    frame: int | None = None,
) -> dict:
    """Safely transform an object in world or local space. Correctly calculates parented object coordinates and supports transactional rollback."""
    return _call("set_object_transform", {
        "reference": reference,
        "location": location,
        "rotation": rotation,
        "scale": scale,
        "mode": mode,
        "space": space,
        "keyframe": keyframe,
        "frame": frame,
    })


@mcp.tool()
def previz_batch_transform(changes: list[dict]) -> dict:
    """Atomically apply multiple transforms. Validates all targets upfront; rolls back completely on any failure."""
    return _call("batch_transform", {"changes": changes})


@mcp.tool()
def previz_capture_views(
    views: list[str] | None = None,
    camera: str | None = None,
    output_dir: str | None = None,
) -> dict:
    """Render multi-angle clean viewport screenshots (top, front, right, perspective, camera) without disrupting user UI."""
    return _call("capture_views", {
        "views": views or ["top", "front", "right", "perspective", "camera"],
        "camera": camera,
        "output_dir": output_dir,
    })


@mcp.tool()
def previz_set_viewport_view(view: str, camera: str | None = None) -> dict:
    """Orient the 3D viewport or camera to top, front, right, perspective, or camera view."""
    return _call("set_viewport_view", {"view": view, "camera": camera})


@mcp.tool()
def previz_collection_create(name: str, parent_collection: str | None = None) -> dict:
    """Create a new collection or retrieve an existing one and link to parent or scene root."""
    return _call("collection_create", {"name": name, "parent_collection": parent_collection})


@mcp.tool()
def previz_collection_move_objects(objects: list[str], target_collection: str) -> dict:
    """Move objects to a target collection, unlinking them from their prior collections."""
    return _call("collection_move_objects", {"objects": objects, "target_collection": target_collection})


@mcp.tool()
def previz_collection_set_visibility(
    collection: str,
    hide_viewport: bool | None = None,
    hide_render: bool | None = None,
) -> dict:
    """Control viewport and render visibility for a collection."""
    return _call("collection_set_visibility", {
        "collection": collection,
        "hide_viewport": hide_viewport,
        "hide_render": hide_render,
    })


@mcp.tool()
def previz_duplicate_object(
    reference: str,
    linked: bool = False,
    name: str | None = None,
    collection: str | None = None,
) -> dict:
    """Duplicate an object with explicit distinction between linked copy and full deep copy."""
    return _call("duplicate_object", {
        "reference": reference,
        "linked": linked,
        "name": name,
        "collection": collection,
    })


@mcp.tool()
def previz_import_file(
    filepath: str,
    collection: str | None = None,
    parent_name: str | None = None,
) -> dict:
    """Safely import 3D files (glb, gltf, fbx, obj, usd) into a collection with optional top-level Chinese parent grouping."""
    return _call("import_file", {
        "filepath": filepath,
        "collection": collection,
        "parent_name": parent_name,
    })


@mcp.tool()
def previz_set_texture_tiling(
    target: str,
    scale_x: float,
    scale_y: float,
    rotation_degrees: float = 0.0,
    mapping_mode: str = "POINT",
    material_slot: int = 0,
) -> dict:
    """Adjust texture tiling scale and rotation non-destructively for Principled BSDF or mapping shader nodes."""
    return _call("set_texture_tiling", {
        "target": target,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "rotation_degrees": rotation_degrees,
        "mapping_mode": mapping_mode,
        "material_slot": material_slot,
    })


@mcp.tool()
def previz_get_task_status(task_id: str) -> dict:
    """Query execution and download status for asset imports and generation tasks."""
    return _call("get_task_status", {"task_id": task_id})


@mcp.tool()
def previz_build_tracking_demo(output_path: str) -> dict:
    """Create and save a separate demo scene with a walking actor, moving car, follow cameras and three camera cuts."""
    return _call("build_tracking_demo", {"output_path": output_path})


def main():
    _ensure_bridge()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
