from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict

import bpy

from .errors import ValidationError
from .fcurves import action_fcurves

UNDO_STACK_LIMIT = 50


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


def _constraint_snapshot(obj: bpy.types.Object) -> list[dict]:
    result = []
    for constraint in obj.constraints:
        if not constraint.name.startswith("AI_PREVIZ_"):
            continue
        item = {
            "type": constraint.type,
            "name": constraint.name,
            "target": constraint.target.name if getattr(constraint, "target", None) else None,
            "influence": float(constraint.influence),
        }
        for attribute in ("use_offset", "track_axis", "up_axis"):
            if hasattr(constraint, attribute):
                item[attribute] = getattr(constraint, attribute)
        result.append(item)
    return result


def _remove_fcurve(action, fc) -> None:
    """Remove an FCurve from a legacy or layered Action."""
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        try:
            legacy.remove(fc)
            return
        except (RuntimeError, ReferenceError):
            pass
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for bag in getattr(strip, "channelbags", []):
                if fc in list(bag.fcurves):
                    bag.fcurves.remove(fc)
                    return


def capture_state() -> dict:
    scene = bpy.context.scene
    objects = {}
    actions = {}
    for obj in scene.objects:
        item = {
            "location": _vec(obj.location), "rotation_mode": obj.rotation_mode,
            "rotation_euler": _vec(obj.rotation_euler), "scale": _vec(obj.scale),
            "hide_viewport": obj.hide_viewport, "hide_render": obj.hide_render,
            "props": _previz_props(obj), "constraints": _constraint_snapshot(obj),
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
    materials = {}
    for material in bpy.data.materials:
        base_color = None
        if material.use_nodes and material.node_tree:
            principled = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
            if principled and "Base Color" in principled.inputs:
                base_color = _vec(principled.inputs["Base Color"].default_value)
        materials[material.name] = {"diffuse_color": _vec(material.diffuse_color), "base_color": base_color}
    return {
        "scene": {
            "frame_current": scene.frame_current, "frame_start": scene.frame_start, "frame_end": scene.frame_end,
            "camera": scene.camera.name if scene.camera else None, "props": _previz_props(scene),
        },
        "objects": objects,
        "actions": actions,
        "materials": materials,
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

    missing = [name for name in state["objects"] if name not in bpy.data.objects]
    if missing:
        raise ValidationError(
            f"无法通过普通事务恢复状态：对象 {missing} 已在操作中被删除。"
            "结构化事务不支持重建任意已删除对象，需使用完整工程恢复点（.blend检查点）进行恢复。"
        )

    # Remove objects created after snapshot.  The snapshot only covers the
    # CURRENT scene, so restrict removal to the current scene as well;
    # iterating bpy.data.objects here would unlink-or-delete objects that
    # belong to other scenes in multi-scene .blend files.
    current_scene = bpy.context.scene
    for obj in list(current_scene.objects):
        if obj.name not in state["objects"]:
            other_scenes = [
                scene for scene in bpy.data.scenes
                if scene != current_scene and obj.name in scene.objects
            ]
            if other_scenes:
                current_scene.objects.unlink(obj)
            else:
                bpy.data.objects.remove(obj, do_unlink=True)

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
        for constraint in list(obj.constraints):
            if constraint.name.startswith("AI_PREVIZ_"):
                obj.constraints.remove(constraint)
        for constraint_state in item.get("constraints", []):
            constraint = obj.constraints.new(constraint_state["type"])
            constraint.name = constraint_state["name"]
            constraint.target = bpy.data.objects.get(constraint_state.get("target"))
            constraint.influence = constraint_state.get("influence", 1.0)
            for attribute in ("use_offset", "track_axis", "up_axis"):
                if attribute in constraint_state and hasattr(constraint, attribute):
                    setattr(constraint, attribute, constraint_state[attribute])
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
        # Drop curves added after the snapshot so the rollback is complete.
        snapshot_keys = {(c["data_path"], c["array_index"]) for c in action_state["curves"]}
        for fc in list(action_fcurves(action)):
            if (fc.data_path, fc.array_index) not in snapshot_keys:
                _remove_fcurve(action, fc)
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
    for material_name, material_state in state.get("materials", {}).items():
        material = bpy.data.materials.get(material_name)
        if not material:
            continue
        material.diffuse_color = material_state["diffuse_color"]
        if material_state.get("base_color") and material.use_nodes and material.node_tree:
            principled = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
            if principled and "Base Color" in principled.inputs:
                principled.inputs["Base Color"].default_value = material_state["base_color"]
    # Purge materials created after the snapshot that are now unreferenced,
    # mirroring how post-snapshot objects are removed above.
    snapshot_materials = set(state.get("materials", {}))
    for material in list(bpy.data.materials):
        if material.name not in snapshot_materials and material.users == 0:
            bpy.data.materials.remove(material)
    from .shot import load_shots, save_shots
    save_shots(load_shots())
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
    checkpoint_path: str | None = None
    task_id: str | None = None
    is_checkpoint_backed: bool = False

    def summary(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k not in {"before_state", "after_state"}}


class TransactionManager:
    def __init__(self):
        self.undo_stack: list[Transaction] = []
        self.redo_stack: list[Transaction] = []

    def prepare(
        self,
        prompt: str,
        intent: dict,
        task_id: str | None = None,
        checkpoint_path: str | None = None,
    ) -> Transaction:
        return Transaction(
            str(uuid.uuid4()),
            prompt,
            intent,
            "PREPARED",
            capture_state(),
            None,
            time.time(),
            checkpoint_path=checkpoint_path,
            task_id=task_id,
            is_checkpoint_backed=bool(checkpoint_path),
        )

    def commit(self, tx: Transaction, validation: dict) -> Transaction:
        tx.after_state = capture_state()
        tx.validation_result = validation
        tx.status = "COMMITTED"
        self.undo_stack.append(tx)
        self.redo_stack.clear()
        # Bound the undo stack: each entry holds two full scene snapshots,
        # which can be very large; drop the oldest beyond the cap.
        while len(self.undo_stack) > UNDO_STACK_LIMIT:
            self.undo_stack.pop(0)
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
