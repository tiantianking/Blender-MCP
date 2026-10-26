from __future__ import annotations

import re


COLORS = {
    "红色": (0.8, 0.03, 0.02), "红": (0.8, 0.03, 0.02),
    "绿色": (0.03, 0.65, 0.12), "绿": (0.03, 0.65, 0.12),
    "蓝色": (0.03, 0.2, 0.85), "蓝": (0.03, 0.2, 0.85),
    "黄色": (0.9, 0.7, 0.03), "黄": (0.9, 0.7, 0.03),
    "白色": (0.9, 0.9, 0.9), "白": (0.9, 0.9, 0.9),
    "黑色": (0.015, 0.015, 0.02), "黑": (0.015, 0.015, 0.02),
    "灰色": (0.3, 0.3, 0.3), "灰": (0.3, 0.3, 0.3),
    "橙色": (0.95, 0.25, 0.02), "橙": (0.95, 0.25, 0.02),
    "紫色": (0.45, 0.08, 0.7), "紫": (0.45, 0.08, 0.7),
}


def _current_actor(context: dict) -> str | None:
    active = context.get("scene", {}).get("active_object")
    for actor in context.get("actors", []):
        if actor.get("name") == active:
            return actor.get("id")
    actors = context.get("actors", [])
    return actors[0].get("id") if len(actors) == 1 else None


def _entity_in_text(text: str, context: dict) -> str | None:
    candidates = [*context.get("actors", []), *context.get("products", []), *context.get("entities", [])]
    matches = []
    for entity in candidates:
        terms = [entity.get("id"), entity.get("name"), *entity.get("aliases", [])]
        if any(str(term).casefold() in text for term in terms if term):
            matches.append(entity.get("id"))
    return matches[0] if len(set(matches)) == 1 else None


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
            factor = float(speed.group(1))
            # In Chinese "慢 2 倍" means play at HALF speed (slow down BY 2x),
            # so invert factors > 1 when slowing; "快 2 倍" keeps the value.
            if "慢" in text and factor > 1:
                factor = 1.0 / factor
            operations.append({"type": "actor_retime", "target": actor, "speed_factor": factor})
    color = next((rgb for name, rgb in COLORS.items() if name in text), None)
    if color and any(word in text for word in ("改成", "变成", "颜色", "设为")):
        target = _entity_in_text(text, context)
        if target:
            operations.append({"type": "material_set_color", "target": target, "red": color[0], "green": color[1], "blue": color[2]})
    if operations:
        return {"intent_version": 1, "operations": operations}
    return None
