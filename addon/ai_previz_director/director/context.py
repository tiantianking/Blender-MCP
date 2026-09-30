from __future__ import annotations

import bpy

from .semantic import auto_role, entity_id, entity_summary
from .shot import load_shots, current_shot
from .fcurves import action_fcurves


def _vec(value) -> list[float]:
    return [round(float(v), 6) for v in value]


def _action_summary(obj: bpy.types.Object) -> dict | None:
    ad = obj.animation_data
    action = ad.action if ad else None
    if not action:
        return None
    curves = action_fcurves(action, getattr(ad, "action_slot", None))
    frames = [kp.co.x for fc in curves for kp in fc.keyframe_points]
    return {
        "name": action.name,
        "users": action.users,
        "frame_range": [min(frames), max(frames)] if frames else None,
        "fcurves": len(curves),
        "keyframes": len(frames),
    }


def _camera_summary(obj: bpy.types.Object) -> dict:
    data = obj.data
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    focus = data.dof.focus_object.name if data.dof.use_dof and data.dof.focus_object else None
    return {
        **entity_summary(obj),
        "lens_mm": data.lens,
        "sensor_width": data.sensor_width,
        "location": _vec(obj.location),
        "evaluated_location": _vec(evaluated.matrix_world.translation),
        "rotation_euler": _vec(obj.rotation_euler),
        "dof": {"enabled": data.dof.use_dof, "focus_target": focus, "focus_distance": data.dof.focus_distance},
        "constraints": [{"name": c.name, "type": c.type, "target": getattr(c.target, "name", None)} for c in obj.constraints],
        "action": _action_summary(obj),
    }


def _object_summary(obj: bpy.types.Object) -> dict:
    summary = {
        **entity_summary(obj),
        "location": _vec(obj.location),
        "rotation_euler": _vec(obj.rotation_euler),
        "dimensions": _vec(obj.dimensions),
        "visible": obj.visible_get(),
        "action": _action_summary(obj),
    }
    if obj.type == "ARMATURE":
        summary["armature"] = obj.name
    return summary


def get_previz_state(detail_ids: list[str] | None = None) -> dict:
    scene = bpy.context.scene
    semantic = [obj for obj in scene.objects if auto_role(obj)]
    details = set(detail_ids or [])
    actors = [_object_summary(o) for o in semantic if auto_role(o) == "ACTOR"]
    products = [_object_summary(o) for o in semantic if auto_role(o) == "PRODUCT"]
    cameras = [_camera_summary(o) for o in scene.objects if o.type == "CAMERA"]
    others = [entity_summary(o) for o in semantic if auto_role(o) not in {"ACTOR", "PRODUCT", "CAMERA"}]
    if details:
        others = [_object_summary(o) if entity_id(o) in details else entity_summary(o) for o in semantic if auto_role(o) not in {"ACTOR", "PRODUCT", "CAMERA"}]
    active = bpy.context.view_layer.objects.active
    shot = current_shot(scene.frame_current)
    return {
        "schema_version": 1,
        "scene": {
            "name": scene.name,
            "current_frame": scene.frame_current,
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
            "fps": scene.render.fps / scene.render.fps_base,
            "active_camera": scene.camera.name if scene.camera else None,
            "selected_objects": [o.name for o in bpy.context.selected_objects],
            "active_object": active.name if active else None,
        },
        "current_shot": shot,
        "cameras": cameras,
        "actors": actors,
        "products": products,
        "shots": load_shots(),
        "entities": others,
        "counts": {"scene_objects": len(scene.objects), "semantic_objects": len(semantic)},
    }

