from __future__ import annotations

import bpy

from .errors import ValidationError
from .semantic import find_entity


def create_collection(name: str, parent_collection: str | None = None) -> dict:
    if not name or not isinstance(name, str):
        raise ValidationError("Collection name must be a non-empty string")

    # If collection already exists, reuse it
    coll = bpy.data.collections.get(name)
    is_new = False
    if not coll:
        coll = bpy.data.collections.new(name=name)
        is_new = True

    parent = None
    if parent_collection:
        parent = bpy.data.collections.get(parent_collection)
        if not parent:
            raise ValidationError(f"Parent collection '{parent_collection}' not found")
        if coll.name not in parent.children:
            parent.children.link(coll)
    else:
        # Check if already linked to scene collection or any collection
        if coll.name not in bpy.context.scene.collection.children:
            is_linked = any(coll.name in p.children for p in bpy.data.collections)
            if not is_linked:
                bpy.context.scene.collection.children.link(coll)

    return {
        "ok": True,
        "name": coll.name,
        "parent": parent.name if parent else bpy.context.scene.collection.name,
        "is_new": is_new,
    }


def move_objects(objects: list[str], target_collection: str) -> dict:
    if not isinstance(objects, list) or not objects:
        raise ValidationError("objects must be a non-empty list of object names or references")

    target = bpy.data.collections.get(target_collection)
    if not target:
        raise ValidationError(f"Target collection '{target_collection}' not found")

    resolved_objs = []
    for ref in objects:
        try:
            obj = find_entity(ref)
        except Exception:
            obj = bpy.data.objects.get(ref)
        if not obj:
            raise ValidationError(f"Object not found: '{ref}'")
        resolved_objs.append(obj)

    moved = []
    for obj in resolved_objs:
        # Unlink from all current collections
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        # Link to target collection
        target.objects.link(obj)
        moved.append(obj.name)

    bpy.context.view_layer.update()
    return {
        "ok": True,
        "target_collection": target.name,
        "moved_objects": moved,
        "count": len(moved),
    }


def set_visibility(
    collection: str,
    hide_viewport: bool | None = None,
    hide_render: bool | None = None,
) -> dict:
    coll = bpy.data.collections.get(collection)
    if not coll:
        raise ValidationError(f"Collection '{collection}' not found")

    if hide_viewport is not None:
        coll.hide_viewport = bool(hide_viewport)
    if hide_render is not None:
        coll.hide_render = bool(hide_render)

    bpy.context.view_layer.update()
    return {
        "ok": True,
        "collection": coll.name,
        "hide_viewport": bool(coll.hide_viewport),
        "hide_render": bool(coll.hide_render),
    }
