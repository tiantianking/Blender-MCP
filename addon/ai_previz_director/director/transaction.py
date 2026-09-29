from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict

import bpy

from .errors import ValidationError
from .fcurves import action_fcurves


def _vec(value):
    return [float(v) for v in value]


def _previz_props(owner) -> dict:
    return {k: owner[k] for k in owner.keys() if str(k).startswith("previz_")}


def _action_snapshot(action: bpy.types.Action, slot=None) -> dict:
    curves = []
    for fc in action_fcurves(action, slot):
        points = []
        for kp in fc.keyframe_points:
            points.append({
                "co": _vec(kp.co), "handle_left": _vec(kp.handle_left), "handle_right": _vec(kp.handle_right),
                "interpolation": kp.interpolation, "easing": kp.easing,
                "handle_left_type": kp.handle_left_type, "handle_right_type": kp.handle_right_type,
            })
        curves.append({"data_path": fc.data_path, "array_index": fc.array_index, "points": points})
    return {"name": action.name, "curves": curves}


def capture_state() -> dict:
    scene = bpy.context.scene
    objects = {}
    actions = {}
    for obj in scene.objects:
        item = {
            "location": _vec(obj.location), "rotation_mode": obj.rotation_mode,
            "rotation_euler": _vec(obj.rotation_euler), "scale": _vec(obj.scale),
            "hide_viewport": obj.hide_viewport, "hide_render": obj.hide_render,
            "props": _previz_props(obj),
        }
        if obj.type == "CAMERA":
            item["camera"] = {
                "lens": float(obj.data.lens), "sensor_width": float(obj.data.sensor_width),
                "dof_enabled": bool(obj.data.dof.use_dof), "focus_distance": float(obj.data.dof.focus_distance),
                "focus_object": obj.data.dof.focus_object.name if obj.data.dof.focus_object else None,
            }
        ad = obj.animation_data
        if ad and ad.action and ad.action.name not in actions:
            actions[ad.action.name] = _action_snapshot(ad.action, getattr(ad, "action_slot", None))
        objects[obj.name] = item
    return {
        "scene": {
            "frame_current": scene.frame_current, "frame_start": scene.frame_start, "frame_end": scene.frame_end,
            "camera": scene.camera.name if scene.camera else None, "props": _previz_props(scene),
        },
        "objects": objects,
        "actions": actions,
    }


def _restore_props(owner, props: dict) -> None:
    for key in [k for k in owner.keys() if str(k).startswith("previz_") and k not in props]:
        del owner[key]
    for key, value in props.items():
        owner[key] = value


def restore_state(state: dict) -> None:
    scene = bpy.context.scene
    ss = state["scene"]
    scene.frame_start, scene.frame_end = int(ss["frame_start"]), int(ss["frame_end"])
    scene.frame_set(int(ss["frame_current"]))
    scene.camera = bpy.data.objects.get(ss["camera"]) if ss.get("camera") else None
    _restore_props(scene, ss.get("props", {}))
    for name, item in state["objects"].items():
        obj = bpy.data.objects.get(name)
        if not obj:
            continue
        obj.location = item["location"]
        obj.rotation_mode = item["rotation_mode"]
        obj.rotation_euler = item["rotation_euler"]
        obj.scale = item["scale"]
        obj.hide_viewport, obj.hide_render = item["hide_viewport"], item["hide_render"]
        _restore_props(obj, item.get("props", {}))
        if obj.type == "CAMERA" and "camera" in item:
            camera = item["camera"]
            obj.data.lens, obj.data.sensor_width = camera["lens"], camera["sensor_width"]
            obj.data.dof.use_dof = camera["dof_enabled"]
            obj.data.dof.focus_distance = camera["focus_distance"]
            obj.data.dof.focus_object = bpy.data.objects.get(camera["focus_object"]) if camera.get("focus_object") else None
    for action_name, action_state in state.get("actions", {}).items():
        action = bpy.data.actions.get(action_name)
        if not action:
            continue
        curve_map = {(fc.data_path, fc.array_index): fc for fc in action_fcurves(action)}
        for curve_state in action_state["curves"]:
            fc = curve_map.get((curve_state["data_path"], curve_state["array_index"]))
            if not fc:
                continue
            fc.keyframe_points.clear()
            for point_state in curve_state["points"]:
                kp = fc.keyframe_points.insert(point_state["co"][0], point_state["co"][1], options={"FAST"})
                kp.handle_left = point_state["handle_left"]
                kp.handle_right = point_state["handle_right"]
                kp.interpolation = point_state["interpolation"]
                kp.easing = point_state["easing"]
                kp.handle_left_type = point_state["handle_left_type"]
                kp.handle_right_type = point_state["handle_right_type"]
            fc.update()
    bpy.context.view_layer.update()


@dataclass
class Transaction:
    transaction_id: str
    user_prompt: str
    intent: dict
    status: str
    before_state: dict
    after_state: dict | None
    timestamp: float
    validation_result: dict | None = None

    def summary(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k not in {"before_state", "after_state"}}


class TransactionManager:
    def __init__(self):
        self.undo_stack: list[Transaction] = []
        self.redo_stack: list[Transaction] = []

    def prepare(self, prompt: str, intent: dict) -> Transaction:
        return Transaction(str(uuid.uuid4()), prompt, intent, "PREPARED", capture_state(), None, time.time())

    def commit(self, tx: Transaction, validation: dict) -> Transaction:
        tx.after_state = capture_state()
        tx.validation_result = validation
        tx.status = "COMMITTED"
        self.undo_stack.append(tx)
        self.redo_stack.clear()
        return tx

    def rollback(self, tx: Transaction, reason: str) -> None:
        restore_state(tx.before_state)
        tx.status = "ROLLED_BACK"
        tx.validation_result = {"ok": False, "reason": reason}

    def undo(self) -> dict:
        if not self.undo_stack:
            raise ValidationError("Nothing to undo")
        tx = self.undo_stack.pop()
        restore_state(tx.before_state)
        tx.status = "UNDONE"
        self.redo_stack.append(tx)
        return tx.summary()

    def redo(self) -> dict:
        if not self.redo_stack:
            raise ValidationError("Nothing to redo")
        tx = self.redo_stack.pop()
        if not tx.after_state:
            raise ValidationError("Transaction has no redo state")
        restore_state(tx.after_state)
        tx.status = "COMMITTED"
        self.undo_stack.append(tx)
        return tx.summary()


MANAGER = TransactionManager()

