from __future__ import annotations

import json

import bpy

from .errors import EntityNotFound, ValidationError

SHOTS_KEY = "previz_shots_json"


def load_shots() -> list[dict]:
    raw = bpy.context.scene.get(SHOTS_KEY, "[]")
    try:
        shots = json.loads(raw)
    except (TypeError, ValueError):
        shots = []
    return sorted((s for s in shots if isinstance(s, dict)), key=lambda s: (s.get("frame_start", 0), s.get("shot_id", "")))


def save_shots(shots: list[dict]) -> None:
    scene = bpy.context.scene
    scene[SHOTS_KEY] = json.dumps(shots, ensure_ascii=False, separators=(",", ":"))
    wanted = {f"PREVIZ_SHOT:{s['shot_id']}": int(s["frame_start"]) for s in shots}
    for marker in list(scene.timeline_markers):
        if marker.name.startswith("PREVIZ_SHOT:") and marker.name not in wanted:
            scene.timeline_markers.remove(marker)
    existing = {m.name: m for m in scene.timeline_markers if m.name.startswith("PREVIZ_SHOT:")}
    for name, frame in wanted.items():
        marker = existing.get(name) or scene.timeline_markers.new(name, frame=frame)
        marker.frame = frame
        shot = next((item for item in shots if f"PREVIZ_SHOT:{item['shot_id']}" == name), None)
        marker.camera = bpy.data.objects.get(shot.get("camera")) if shot and shot.get("camera") else None


def _shot_ref(reference: str | None) -> dict:
    shots = load_shots()
    if not shots:
        raise EntityNotFound("No previz shots exist")
    ref = (reference or "current").casefold()
    if ref in {"last", "最后", "最后一个镜头"}:
        return shots[-1]
    if ref in {"current", "当前", "当前镜头"}:
        shot = current_shot(bpy.context.scene.frame_current)
        if shot:
            return shot
    for shot in shots:
        if str(shot.get("shot_id", "")).casefold() == ref:
            return shot
    available = [str(s.get("shot_id")) for s in shots]
    raise EntityNotFound(f"Shot not found: {reference}. Available shot_ids: {available}")


def current_shot(frame: int) -> dict | None:
    matches = [s for s in load_shots() if int(s.get("frame_start", 0)) <= frame <= int(s.get("frame_end", -1))]
    return matches[-1] if matches else None


def create_shot(shot_id: str, frame_start: int, frame_end: int, camera: str | None = None, subject: str | None = None, shot_type: str | None = None) -> dict:
    if frame_end < frame_start:
        raise ValidationError("Shot end precedes start")
    shots = load_shots()
    if any(s.get("shot_id") == shot_id for s in shots):
        raise ValidationError(f"Shot already exists: {shot_id}")
    shot = {"shot_id": shot_id, "frame_start": int(frame_start), "frame_end": int(frame_end), "camera": camera, "subject": subject, "focus_target": subject, "shot_type": shot_type or "UNSPECIFIED"}
    shots.append(shot)
    save_shots(shots)
    return shot


def update_shot(reference: str | None, **changes) -> dict:
    shots = load_shots()
    target = _shot_ref(reference)
    if "frame_start" in changes and "frame_end" in changes and changes["frame_end"] < changes["frame_start"]:
        raise ValidationError("Shot end precedes start")
    for shot in shots:
        if shot.get("shot_id") == target.get("shot_id"):
            shot.update({k: v for k, v in changes.items() if v is not None})
            target = shot
            break
    save_shots(shots)
    return target


def hold_shot(reference: str | None, hold_frames: int) -> dict:
    shot = _shot_ref(reference)
    old_end = int(shot["frame_end"])
    updated = update_shot(reference, frame_end=old_end + int(hold_frames))
    scene = bpy.context.scene
    scene.frame_end = max(scene.frame_end, updated["frame_end"])
    return updated

