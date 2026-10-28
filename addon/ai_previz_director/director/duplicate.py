from __future__ import annotations

import bpy

from .errors import ValidationError
from .semantic import resolve_object


def duplicate_object(
    reference: str,
    linked: bool = False,
    name: str | None = None,
    collection: str | None = None,
) -> dict:
    obj = resolve_object(reference)

    # Linked copy vs Full copy
    new_obj = obj.copy()
    if not linked and obj.data:
        new_obj.data = obj.data.copy()

    if name:
        new_obj.name = name

    target_coll = None
    if collection:
        target_coll = bpy.data.collections.get(collection)
        if not target_coll:
            raise ValidationError(f"Target collection '{collection}' not found")
    elif obj.users_collection:
        target_coll = obj.users_collection[0]
    else:
        target_coll = bpy.context.scene.collection

    target_coll.objects.link(new_obj)
    bpy.context.view_layer.update()

    return {
        "ok": True,
        "name": new_obj.name,
        "original": obj.name,
        "linked": linked,
        "collection": target_coll.name,
        "location": [round(v, 6) for v in new_obj.location],
        "dimensions": [round(v, 6) for v in new_obj.dimensions],
    }
