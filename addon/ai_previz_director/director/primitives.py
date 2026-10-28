from __future__ import annotations

import bpy

from .errors import EntityNotFound, ValidationError
from .semantic import find_entity

# Supported primitive kinds -> (bpy.ops.mesh entrypoint, size argument name).
# `size` is interpreted as the overall bounding extent (diameter) in world
# units so agents can reason about it without knowing per-primitive radii.
_PRIMITIVES: dict[str, tuple[str, dict]] = {
    "CUBE": ("primitive_cube_add", {"size": "extent"}),
    "SPHERE": ("primitive_uv_sphere_add", {"radius": "half"}),
    "CYLINDER": ("primitive_cylinder_add", {"radius": "half", "depth": "extent"}),
    "CONE": ("primitive_cone_add", {"radius": "half", "depth": "extent"}),
    "PLANE": ("primitive_plane_add", {"size": "extent"}),
    "TORUS": ("primitive_torus_add", {"major_radius": "half", "minor_radius": "tenth"}),
    "MONKEY": ("primitive_monkey_add", {"size": "extent"}),
}

VALID_PRIMITIVES = {*_PRIMITIVES, "EMPTY"}


def create_object(
    name: str | None,
    primitive: str,
    location: tuple[float | None, float | None, float | None] | None = None,
    size: float = 1.0,
) -> dict:
    """Create a primitive object in the current scene. Runs inside a Director
    transaction, so previz_undo cleanly removes it."""
    kind = str(primitive or "").upper().strip()
    if kind not in VALID_PRIMITIVES:
        raise ValidationError(
            f"Unsupported primitive '{primitive}'. Must be one of: {sorted(VALID_PRIMITIVES)}"
        )
    try:
        extent = float(size)
    except (TypeError, ValueError):
        raise ValidationError(f"size must be numeric, got: {size!r}") from None
    if not 0.01 <= extent <= 1000:
        raise ValidationError(f"size must be within [0.01, 1000], got {extent}")

    scene = bpy.context.scene
    existing = {obj.name for obj in scene.objects}

    if kind == "EMPTY":
        obj = bpy.data.objects.new(name=name or None, object_data=None)
        scene.collection.objects.link(obj)
    else:
        op_name, size_args = _PRIMITIVES[kind]
        kwargs: dict[str, float] = {}
        for arg, mode in size_args.items():
            if mode == "extent":
                kwargs[arg] = extent
            elif mode == "half":
                kwargs[arg] = extent / 2.0
            elif mode == "tenth":
                kwargs[arg] = max(extent / 10.0, 0.001)
        operator = getattr(bpy.ops.mesh, op_name, None)
        if operator is None:
            raise ValidationError(f"Blender build lacks operator mesh.{op_name}")
        operator(**kwargs)
        # Operators make the new object active, but prefer a set-diff which is
        # robust in headless/background contexts.
        created = [obj for obj in scene.objects if obj.name not in existing]
        obj = created[0] if created else bpy.context.active_object
        if obj is None:
            raise ValidationError("Primitive creation produced no object")
        if name:
            obj.name = name

    if location:
        coords = []
        for axis, value in zip(("x", "y", "z"), location):
            if value is not None:
                coords.append(float(value))
            else:
                coords.append(float(getattr(obj.location, axis)))
        obj.location = coords

    bpy.context.view_layer.update()
    return {
        "name": obj.name,
        "primitive": kind,
        "location": [round(float(v), 6) for v in obj.location],
        "dimensions": [round(float(v), 6) for v in obj.dimensions],
        "size_requested": extent,
    }


def delete_object(reference: str, recursive: bool = False) -> dict:
    """Delete an object (optionally its whole child hierarchy). Runs inside a
    Director transaction, but note: previz_undo CANNOT resurrect deleted
    geometry — restoring deletions requires the .blend checkpoint."""
    obj = find_entity(reference)
    victims = [obj]
    if recursive:
        victims.extend(obj.children_recursive)
    names = [victim.name for victim in victims]
    for victim in victims:
        bpy.data.objects.remove(victim, do_unlink=True)
    bpy.context.view_layer.update()
    return {"deleted": names, "count": len(names), "recursive": bool(recursive)}


def rename_object(reference: str, new_name: str) -> dict:
    """Rename an object. Atomic: refuses to collide with an existing name and
    restores the previous name if anything fails. Not part of previz_undo."""
    if not new_name or not isinstance(new_name, str):
        raise ValidationError("new_name must be a non-empty string")
    obj = find_entity(reference)
    collision = bpy.data.objects.get(new_name)
    if collision and collision != obj:
        raise ValidationError(
            f"Name '{new_name}' is already used by object '{collision.name}'. "
            "Pick a different name."
        )
    old_name = obj.name
    try:
        obj.name = new_name
    except Exception as exc:
        obj.name = old_name
        raise ValidationError(f"Rename failed: {exc}") from exc
    if obj.name != new_name:
        # Blender silently renamed (e.g. trailing dot); report the real name.
        restored = obj.name
        obj.name = old_name
        raise ValidationError(
            f"Blender adjusted the requested name to '{restored}'. "
            "Use that name or choose another."
        )
    return {"ok": True, "old_name": old_name, "new_name": obj.name}


__all__ = ["create_object", "delete_object", "rename_object", "VALID_PRIMITIVES", "EntityNotFound"]
