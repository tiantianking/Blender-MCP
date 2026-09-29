from __future__ import annotations

import bpy

from . import animation, camera, shot
from .errors import PrevizError, ValidationError
from .intent_schema import validate_intent
from .semantic import find_entity, entity_id
from .transaction import MANAGER
from .validation import validate_scene


def _camera_ref(op: dict) -> str:
    return op.get("target") or "current_camera"


def _apply(op: dict) -> dict:
    kind = op["type"]
    if kind == "camera_set_lens":
        return camera.set_lens(_camera_ref(op), op["lens_mm"], op.get("subject"), op.get("preserve_subject_framing", False))
    if kind == "camera_dolly":
        return camera.dolly(_camera_ref(op), op["distance"])
    if kind == "camera_orbit":
        return camera.orbit(_camera_ref(op), op["subject"], op["angle_degrees"])
    if kind == "camera_look_at":
        cam = find_entity(_camera_ref(op), {"CAMERA"})
        subject = find_entity(op["subject"])
        camera.look_at(cam, subject)
        return {"camera": cam.name, "subject": subject.name}
    if kind == "camera_frame_subject":
        return camera.frame_subject(_camera_ref(op), op["subject"], op.get("padding", 0.15))
    if kind == "actor_retime":
        return animation.retime_speed(op["target"], op["speed_factor"], op.get("frame_start"), op.get("frame_end"))
    if kind == "animation_shift":
        return animation.shift(op["target"], op["frame_delta"], op.get("frame_start"), op.get("frame_end"))
    if kind == "animation_scale_time":
        return animation.scale_time(op["target"], op["time_scale"], op.get("frame_start"), op.get("frame_end"))
    if kind == "animation_insert_hold":
        return animation.insert_hold(op["target"], op["frame_end"], op["hold_frames"])
    if kind == "shot_create":
        cam = find_entity(op.get("target") or "current_camera", {"CAMERA"})
        return shot.create_shot(op["shot_id"], op["frame_start"], op["frame_end"], cam.name, op.get("subject"), op.get("shot_type"))
    if kind == "shot_set_range":
        return shot.update_shot(op["shot"], frame_start=op["frame_start"], frame_end=op["frame_end"])
    if kind == "shot_set_camera":
        cam = find_entity(op["target"], {"CAMERA"})
        return shot.update_shot(op["shot"], camera=cam.name)
    if kind in {"shot_product_closeup", "shot_actor_closeup"}:
        roles = {"PRODUCT"} if kind == "shot_product_closeup" else {"ACTOR"}
        subject = find_entity(op["target"], roles)
        result = camera.frame_subject("current_camera", entity_id(subject), op.get("padding", 0.1))
        updated = shot.update_shot(op.get("shot") or "last", subject=entity_id(subject), focus_target=entity_id(subject), shot_type="PRODUCT_CLOSEUP" if roles == {"PRODUCT"} else "ACTOR_CLOSEUP")
        if op.get("hold_frames"):
            updated = shot.hold_shot(op.get("shot") or "last", op["hold_frames"])
        return {"framing": result, "shot": updated}
    if kind == "shot_hold":
        return shot.hold_shot(op.get("shot") or "last", op["hold_frames"])
    raise ValidationError(f"Unhandled operation: {kind}")


def execute_intent(intent: dict, user_prompt: str = "") -> dict:
    validate_intent(intent)
    operations = intent["operations"]
    if operations[0]["type"] == "previz_undo":
        return {"ok": True, "transaction": MANAGER.undo(), "results": []}
    if operations[0]["type"] == "previz_redo":
        return {"ok": True, "transaction": MANAGER.redo(), "results": []}
    tx = MANAGER.prepare(user_prompt, intent)
    tx.status = "APPLIED"
    results = []
    try:
        for op in operations:
            results.append({"type": op["type"], "result": _apply(op)})
        bpy.context.view_layer.update()
        validation = validate_scene()
        if not validation["ok"]:
            raise ValidationError("; ".join(validation["errors"]))
        tx.status = "VALIDATED"
        MANAGER.commit(tx, validation)
        return {"ok": True, "transaction": tx.summary(), "results": results, "validation": validation}
    except Exception as exc:
        MANAGER.rollback(tx, str(exc))
        if isinstance(exc, PrevizError):
            raise
        raise PrevizError(str(exc)) from exc

