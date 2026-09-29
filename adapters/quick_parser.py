from __future__ import annotations

import re


def _current_actor(context: dict) -> str | None:
    active = context.get("scene", {}).get("active_object")
    for actor in context.get("actors", []):
        if actor.get("name") == active:
            return actor.get("id")
    actors = context.get("actors", [])
    return actors[0].get("id") if len(actors) == 1 else None


def compile_quick(prompt: str, context: dict) -> dict | None:
    text = prompt.strip().casefold()
    if any(word in text for word in ("撤销", "undo")):
        return {"intent_version": 1, "operations": [{"type": "previz_undo"}]}
    if any(word in text for word in ("重做", "redo")):
        return {"intent_version": 1, "operations": [{"type": "previz_redo"}]}
    operations = []
    lens = re.search(r"(?<!\d)(\d{2,3}(?:\.\d+)?)\s*mm\b", text)
    if lens:
        operations.append({"type": "camera_set_lens", "target": "current_camera", "lens_mm": float(lens.group(1)), "preserve_subject_framing": False})
    orbit = re.search(r"(?:向)?(左|右).*?绕.*?(-?\d+(?:\.\d+)?)\s*度", text)
    if orbit:
        subject = context.get("current_shot", {}).get("subject") if context.get("current_shot") else None
        subject = subject or (_current_actor(context))
        if subject:
            angle = float(orbit.group(2)) * (1 if orbit.group(1) == "左" else -1)
            operations.append({"type": "camera_orbit", "target": "current_camera", "subject": subject, "angle_degrees": angle})
    if "靠近" in text or "推进" in text or "dolly in" in text:
        operations.append({"type": "camera_dolly", "target": "current_camera", "distance": 0.5})
    speed = re.search(r"(?:速度|原来).*?(0?\.\d+|\d+(?:\.\d+)?)\s*倍", text)
    if speed and ("慢" in text or "快" in text):
        actor = _current_actor(context)
        if actor:
            operations.append({"type": "actor_retime", "target": actor, "speed_factor": float(speed.group(1))})
    if operations:
        return {"intent_version": 1, "operations": operations}
    return None

