from __future__ import annotations

import math
import mathutils
import bpy

from .errors import AmbiguousEntity, EntityNotFound, ValidationError
from .semantic import find_entity


def _vec(val, precision: int = 6) -> list[float]:
    return [round(float(v), precision) for v in val]


def _resolve_object(reference: str) -> bpy.types.Object:
    if not reference or not isinstance(reference, str):
        raise ValidationError(f"Invalid object reference: {reference}")
    try:
        return find_entity(reference)
    except EntityNotFound:
        pass  # fall through to the raw bpy.data lookup below
    # AmbiguousEntity must propagate: its candidate list is exactly what the
    # calling agent needs to disambiguate the reference on the next try.
    obj = bpy.data.objects.get(reference)
    if obj:
        return obj
    raise ValidationError(f"Object not found: '{reference}'")


def _validate_change(change: dict, index: int | None = None) -> bpy.types.Object:
    prefix = f"Change[{index}]: " if index is not None else ""
    if not isinstance(change, dict):
        raise ValidationError(f"{prefix}must be an object")

    ref = change.get("reference")
    if not ref:
        raise ValidationError(f"{prefix}missing required field 'reference'")

    obj = _resolve_object(ref)

    mode = change.get("mode", "absolute")
    if mode not in {"absolute", "relative"}:
        raise ValidationError(f"{prefix}mode must be 'absolute' or 'relative', got '{mode}'")

    space = change.get("space", "world")
    if space not in {"world", "local"}:
        raise ValidationError(f"{prefix}space must be 'world' or 'local', got '{space}'")

    for field in ("location", "rotation", "scale"):
        val = change.get(field)
        if val is not None:
            if not isinstance(val, (list, tuple)) or len(val) != 3 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in val):
                raise ValidationError(f"{prefix}'{field}' must be a list of 3 numbers")

    frame = change.get("frame")
    if frame is not None and (isinstance(frame, bool) or not isinstance(frame, int)):
        raise ValidationError(f"{prefix}'frame' must be an integer")

    return obj


def _apply_transform_single(
    obj: bpy.types.Object,
    location: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
    mode: str = "absolute",
    space: str = "world",
    keyframe: bool = False,
    frame: int | None = None,
) -> dict:
    scene = bpy.context.scene
    rot_mode = obj.rotation_mode if obj.rotation_mode in {'XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX'} else 'XYZ'

    before_loc = _vec(obj.location)
    before_world_loc = _vec(obj.matrix_world.translation)

    if space == "world":
        cur_mat = obj.matrix_world.copy()
        cur_trans = cur_mat.translation.copy()
        cur_rot = cur_mat.to_euler(rot_mode)
        cur_scale = cur_mat.to_scale()

        if mode == "absolute":
            new_trans = mathutils.Vector(location) if location is not None else cur_trans
            new_rot = mathutils.Euler(rotation, rot_mode) if rotation is not None else cur_rot
            new_scale = mathutils.Vector(scale) if scale is not None else cur_scale
        else:  # relative world
            new_trans = cur_trans + mathutils.Vector(location) if location is not None else cur_trans
            if rotation is not None:
                delta_rot_mat = mathutils.Euler(rotation, rot_mode).to_matrix().to_4x4()
                new_rot = (delta_rot_mat @ cur_mat.to_3x3().to_4x4()).to_euler(rot_mode)
            else:
                new_rot = cur_rot
            if scale is not None:
                new_scale = mathutils.Vector((cur_scale.x * scale[0], cur_scale.y * scale[1], cur_scale.z * scale[2]))
            else:
                new_scale = cur_scale

        target_world_mat = mathutils.Matrix.LocRotScale(new_trans, new_rot, new_scale)
        obj.matrix_world = target_world_mat
    else:  # space == "local"
        if mode == "absolute":
            if location is not None:
                obj.location = mathutils.Vector(location)
            if rotation is not None:
                obj.rotation_euler = mathutils.Euler(rotation, rot_mode)
            if scale is not None:
                obj.scale = mathutils.Vector(scale)
        else:  # relative local
            if location is not None:
                obj.location += mathutils.Vector(location)
            if rotation is not None:
                obj.rotation_euler = mathutils.Euler(
                    [a + b for a, b in zip(obj.rotation_euler, rotation)],
                    rot_mode,
                )
            if scale is not None:
                obj.scale = mathutils.Vector((obj.scale.x * scale[0], obj.scale.y * scale[1], obj.scale.z * scale[2]))

    bpy.context.view_layer.update()

    if keyframe:
        target_frame = frame if frame is not None else scene.frame_current
        if location is not None:
            obj.keyframe_insert("location", frame=target_frame)
        if rotation is not None:
            obj.keyframe_insert("rotation_euler", frame=target_frame)
        if scale is not None:
            obj.keyframe_insert("scale", frame=target_frame)

    after_loc = _vec(obj.location)
    after_world_loc = _vec(obj.matrix_world.translation)

    return {
        "name": obj.name,
        "parent": obj.parent.name if obj.parent else None,
        "location": after_loc,
        "world_location": after_world_loc,
        "rotation_euler": _vec(obj.rotation_euler),
        "scale": _vec(obj.scale),
        "before_location": before_loc,
        "before_world_location": before_world_loc,
        "keyframed": keyframe,
        "frame": frame if keyframe else None,
    }


def set_object_transform(
    reference: str,
    location: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
    mode: str = "absolute",
    space: str = "world",
    keyframe: bool = False,
    frame: int | None = None,
) -> dict:
    change = {
        "reference": reference,
        "location": location,
        "rotation": rotation,
        "scale": scale,
        "mode": mode,
        "space": space,
        "keyframe": keyframe,
        "frame": frame,
    }
    obj = _validate_change(change)
    before_state = {
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "matrix_world": obj.matrix_world.copy(),
    }

    try:
        res = _apply_transform_single(
            obj=obj,
            location=location,
            rotation=rotation,
            scale=scale,
            mode=mode,
            space=space,
            keyframe=keyframe,
            frame=frame,
        )
        return {"ok": True, "result": res}
    except Exception as exc:
        obj.matrix_world = before_state["matrix_world"]
        obj.location = before_state["location"]
        obj.rotation_euler = before_state["rotation_euler"]
        obj.scale = before_state["scale"]
        bpy.context.view_layer.update()
        raise ValidationError(f"Failed to transform '{obj.name}': {exc}") from exc


def batch_transform(changes: list[dict]) -> dict:
    if not isinstance(changes, list) or len(changes) == 0:
        raise ValidationError("batch_transform requires a non-empty list of changes")

    # Step 1: Strict atomic pre-validation of all targets
    validated_objs: list[bpy.types.Object] = []
    for idx, change in enumerate(changes):
        obj = _validate_change(change, index=idx)
        validated_objs.append(obj)

    # Step 2: Capture initial state of all involved objects for atomic rollback
    snapshots = {}
    for obj in validated_objs:
        if obj.name not in snapshots:
            snapshots[obj.name] = {
                "obj": obj,
                "location": list(obj.location),
                "rotation_euler": list(obj.rotation_euler),
                "scale": list(obj.scale),
                "matrix_world": obj.matrix_world.copy(),
            }

    # Step 3: Apply transforms with rollback guarantee
    results = []
    try:
        for change, obj in zip(changes, validated_objs):
            res = _apply_transform_single(
                obj=obj,
                location=change.get("location"),
                rotation=change.get("rotation"),
                scale=change.get("scale"),
                mode=change.get("mode", "absolute"),
                space=change.get("space", "world"),
                keyframe=change.get("keyframe", False),
                frame=change.get("frame"),
            )
            results.append(res)
        bpy.context.view_layer.update()
        return {"ok": True, "count": len(results), "results": results}
    except Exception as exc:
        # Atomic rollback
        for snap in snapshots.values():
            o = snap["obj"]
            o.matrix_world = snap["matrix_world"]
            o.location = snap["location"]
            o.rotation_euler = snap["rotation_euler"]
            o.scale = snap["scale"]
        bpy.context.view_layer.update()
        raise ValidationError(f"Batch transform aborted and rolled back: {exc}") from exc
