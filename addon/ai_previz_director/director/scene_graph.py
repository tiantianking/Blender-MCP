from __future__ import annotations

import mathutils
import bpy

from .errors import ValidationError
from .semantic import auto_role, entity_id


def _vec(val, precision: int = 6) -> list[float]:
    return [round(float(v), precision) for v in val]


def _mat4(mat, precision: int = 6) -> list[list[float]]:
    return [[round(float(val), precision) for val in row] for row in mat]


def _get_aabb(obj: bpy.types.Object) -> dict:
    if obj.type == "MESH" and obj.data and len(obj.data.vertices) > 0:
        corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
        min_x = min(c.x for c in corners)
        max_x = max(c.x for c in corners)
        min_y = min(c.y for c in corners)
        max_y = max(c.y for c in corners)
        min_z = min(c.z for c in corners)
        max_z = max(c.z for c in corners)
    else:
        loc = obj.matrix_world.translation
        min_x = max_x = loc.x
        min_y = max_y = loc.y
        min_z = max_z = loc.z

    return {
        "min": [round(min_x, 6), round(min_y, 6), round(min_z, 6)],
        "max": [round(max_x, 6), round(max_y, 6), round(max_z, 6)],
        "center": [round((min_x + max_x) / 2.0, 6), round((min_y + max_y) / 2.0, 6), round((min_z + max_z) / 2.0, 6)],
        "size": [round(max_x - min_x, 6), round(max_y - min_y, 6), round(max_z - min_z, 6)],
    }


def _get_collection_objects(collection: bpy.types.Collection) -> set[bpy.types.Object]:
    objects = set(collection.objects)
    for child in collection.children:
        objects.update(_get_collection_objects(child))
    return objects


def get_scene_graph(
    cursor: str | None = None,
    limit: int = 200,
    collection: str | None = None,
    include_hidden: bool = True,
    include_materials: bool = False,
) -> dict:
    scene = bpy.context.scene

    if collection:
        target_coll = bpy.data.collections.get(collection)
        if not target_coll:
            raise ValidationError(f"Collection '{collection}' not found")
        candidates = list(_get_collection_objects(target_coll))
    else:
        candidates = list(scene.objects)

    if not include_hidden:
        candidates = [obj for obj in candidates if not obj.hide_viewport and obj.visible_get()]

    candidates.sort(key=lambda o: o.name)
    total = len(candidates)

    limit = max(1, min(int(limit), 1000))
    offset = 0
    if cursor is not None and str(cursor).strip() != "":
        try:
            offset = max(0, int(cursor))
        except ValueError:
            raise ValidationError(f"Invalid cursor format: '{cursor}' (expected integer offset)")

    paged = candidates[offset : offset + limit]
    next_offset = offset + len(paged)
    has_more = next_offset < total
    next_cursor = str(next_offset) if has_more else None

    objects_data = []
    for obj in paged:
        role = auto_role(obj)
        sem_id = entity_id(obj) if role else None
        aliases = list(obj.get("previz_aliases", [])) if "previz_aliases" in obj else []

        materials = []
        if include_materials or len(obj.material_slots) > 0:
            materials = [slot.material.name for slot in obj.material_slots if slot.material]

        vert_count = len(obj.data.vertices) if obj.type == "MESH" and obj.data else 0
        face_count = len(obj.data.polygons) if obj.type == "MESH" and obj.data else 0

        item = {
            "name": obj.name,
            "reference": sem_id or obj.name,
            "type": obj.type,
            "parent": obj.parent.name if obj.parent else None,
            "children": [c.name for c in obj.children],
            "collections": [c.name for c in obj.users_collection],
            "location": _vec(obj.location),
            "rotation": _vec(obj.rotation_euler),
            "rotation_mode": obj.rotation_mode,
            "scale": _vec(obj.scale),
            "world_matrix": _mat4(obj.matrix_world),
            "dimensions": _vec(obj.dimensions),
            "aabb": _get_aabb(obj),
            "visibility": {
                "hide_viewport": bool(obj.hide_viewport),
                "hide_render": bool(obj.hide_render),
                "visible": bool(obj.visible_get()),
            },
            "materials": materials,
            "vertex_count": vert_count,
            "face_count": face_count,
            "semantic": {"role": role, "id": sem_id, "aliases": aliases} if role else None,
        }
        objects_data.append(item)

    return {
        "ok": True,
        "scene": {
            "name": scene.name,
            "current_frame": scene.frame_current,
            "active_camera": scene.camera.name if scene.camera else None,
        },
        "cursor": cursor,
        "next_cursor": next_cursor,
        "total": total,
        "limit": limit,
        "truncated": has_more,
        "objects": objects_data,
    }
