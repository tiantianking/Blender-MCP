from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image

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


def _intent(operation: dict, task_label: str | None = None) -> dict:
    """Build an execute_intent call. The recorded prompt identifies the
    operation type (and optional task label) so undo history stays readable
    instead of every entry reading 'MCP structured operation'."""
    prompt = f"structured:{operation.get('type', 'operation')}"
    if task_label:
        prompt = f"{prompt} ({task_label})"
    return _call("execute_intent", {"intent": {"intent_version": 1, "operations": [operation]}, "prompt": prompt})


@mcp.tool()
def previz_get_state(detail_ids: list[str] | None = None) -> dict:
    """Return compact semantic previz state: tagged actors, products, cameras and shots
    as light summaries (id/name/role/aliases). Pass detail_ids to expand specific
    entities with full transforms, materials and animation info — keeping large
    scenes cheap to read while still allowing deep inspection on demand."""
    return _call("get_state", {"detail_ids": detail_ids or []})


@mcp.tool()
def previz_set_frame(frame: int) -> dict:
    """Set the current frame and return the resulting semantic state, including the active shot camera."""
    return _call("set_frame", {"frame": frame})


@mcp.tool()
def previz_find_entity(reference: str) -> dict:
    """Resolve a semantic id, object name or alias to its stable reference without modifying Blender.

    Accepted magic references: 'current_camera' (or 当前摄影机/当前相机) for the
    active camera, 'active_object' (or 当前对象) for the active selection.
    Regular names match object name, previz_id and aliases case-insensitively."""
    return _call("find_entity", {"reference": reference})


@mcp.tool()
def previz_tag_entity(reference: str, role: str, entity_id: str, aliases: list[str] | None = None) -> dict:
    """Persist a semantic role, stable id and aliases on a Blender object."""
    return _call("tag_entity", {"reference": reference, "role": role, "entity_id": entity_id, "aliases": aliases or []})


@mcp.tool()
def camera_set_lens(lens_mm: float, camera: str = "current_camera", subject: str | None = None, preserve_subject_framing: bool = False) -> dict:
    """Set camera focal length in millimeters (valid 8-600; e.g. 24 wide, 50 normal, 85 portrait).
    Optionally preserve a subject's framing by adjusting camera distance."""
    op = {"type": "camera_set_lens", "target": camera, "lens_mm": lens_mm, "preserve_subject_framing": preserve_subject_framing}
    if subject:
        op["subject"] = subject
    return _intent(op)


@mcp.tool()
def camera_dolly(distance: float, camera: str = "current_camera") -> dict:
    """Move a camera along its viewing direction, in world units (meters).
    POSITIVE values move TOWARD the subject, negative values pull back."""
    return _intent({"type": "camera_dolly", "target": camera, "distance": distance})


@mcp.tool()
def camera_orbit(subject: str, angle_degrees: float, camera: str = "current_camera") -> dict:
    """Reposition a camera around a subject on world Z while keeping it aimed at the subject.

    Direction convention: POSITIVE angle orbits counterclockwise (camera moves
    to the LEFT of the subject); NEGATIVE angle orbits clockwise (to the RIGHT).
    Example: orbit right by 30 degrees -> angle_degrees=-30.
    """
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
def previz_capture_view(output_path: str, return_image: bool = True):
    """Render a clean camera still without Blender UI overlays.

    Returns the result dict PLUS the rendered PNG as an image content block
    (when return_image is true), so the calling agent can visually verify the
    scene directly without a separate file-reading step."""
    result = _call("capture_view", {"output_path": output_path})
    if return_image and result.get("ok") and result.get("result", {}).get("path"):
        path = result["result"]["path"]
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                return [result, Image(data=handle.read(), format="png")]
    return result


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
    include_matrix: bool = False,
) -> dict:
    """Query the scene tree with pagination, hierarchy, world AABB bounds and semantic tags.

    Returns name/type/parent/children/transform/aabb per object. The 4x4
    world_matrix is omitted by default to keep responses compact (aabb already
    encodes world-space extents); set include_matrix=true when the full matrix
    is required."""
    return _call("get_scene_graph", {
        "cursor": cursor,
        "limit": limit,
        "collection": collection,
        "include_hidden": include_hidden,
        "include_materials": include_materials,
        "include_matrix": include_matrix,
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
    rotation_degrees: list[float] | None = None,
) -> dict:
    """Safely transform an object in world or local space with transactional rollback.

    UNITS: location is in world units (meters); scale is a multiplier (1.0 = unchanged).
    ROTATION IS IN RADIANS (Blender convention: 90 degrees = 1.5708, 180 = 3.1416).
    Prefer the rotation_degrees parameter (Euler XYZ, degrees) for human-style angles.
    mode: 'absolute' sets values, 'relative' adds to current. space: 'world' or 'local'.
    """
    if rotation is not None and rotation_degrees is not None:
        raise ValueError("Pass either rotation (radians) or rotation_degrees, not both")
    if rotation_degrees is not None:
        rotation = [math.radians(float(v)) for v in rotation_degrees]
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
    return_images: bool = False,
    max_images: int = 2,
):
    """Render multi-angle clean viewport screenshots (top, front, right, perspective, camera) without disrupting user UI.

    With return_images=true the rendered PNGs are ALSO returned as image
    content blocks (up to max_images, camera view first) so the agent can
    visually inspect the scene. Keep max_images small to control token cost."""
    result = _call("capture_views", {
        "views": views or ["top", "front", "right", "perspective", "camera"],
        "camera": camera,
        "output_dir": output_dir,
    })
    if return_images and result.get("ok"):
        blocks = [result]
        rendered = [v for v in result.get("views", []) if v.get("success") and v.get("path") and os.path.isfile(v["path"])]
        # Camera view first for verification value, then the rest
        rendered.sort(key=lambda v: 0 if v.get("view") == "camera" else 1)
        for view in rendered[: max(1, int(max_images))]:
            with open(view["path"], "rb") as handle:
                blocks.append(Image(data=handle.read(), format="png"))
        return blocks
    return result


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
def previz_build_tracking_demo(output_path: str) -> dict:
    """Create and save a separate demo scene with a walking actor, moving car, follow cameras and three camera cuts."""
    return _call("build_tracking_demo", {"output_path": output_path})


def main():
    _ensure_bridge()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
