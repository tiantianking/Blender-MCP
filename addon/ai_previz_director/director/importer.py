from __future__ import annotations

import os
from pathlib import Path

import bpy

from .errors import ValidationError

ALLOWED_FORMATS = {".glb", ".gltf", ".fbx", ".obj", ".usd", ".usda", ".usdc"}


def import_file(
    filepath: str,
    collection: str | None = None,
    parent_name: str | None = None,
) -> dict:
    if not filepath or not isinstance(filepath, str):
        raise ValidationError("filepath must be a non-empty string")

    path = Path(filepath).expanduser().resolve()
    if not path.is_absolute():
        raise ValidationError(f"filepath must be an absolute path: '{filepath}'")

    ext = path.suffix.lower()
    if ext == ".blend":
        raise ValidationError("Prohibited: Cannot import or replace current project with .blend file directly.")

    if not path.is_file():
        raise ValidationError(f"File not found: '{path}'")

    if ext not in ALLOWED_FORMATS:
        raise ValidationError(f"Unsupported format '{ext}'. Allowed formats: {sorted(ALLOWED_FORMATS)}")

    target_coll = None
    if collection:
        target_coll = bpy.data.collections.get(collection)
        if not target_coll:
            target_coll = bpy.data.collections.new(name=collection)
            bpy.context.scene.collection.children.link(target_coll)

    existing_objects = set(bpy.data.objects.keys())

    # Call format-specific importer
    try:
        if ext in {".glb", ".gltf"}:
            bpy.ops.import_scene.gltf(filepath=str(path))
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(path))
        elif ext == ".obj":
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=str(path))
            elif hasattr(bpy.ops.import_scene, "obj"):
                bpy.ops.import_scene.obj(filepath=str(path))
            else:
                raise ValidationError("No OBJ importer operator found in current Blender build")
        elif ext in {".usd", ".usda", ".usdc"}:
            if hasattr(bpy.ops.wm, "usd_import"):
                bpy.ops.wm.usd_import(filepath=str(path))
            else:
                raise ValidationError("No USD importer operator found in current Blender build")
    except Exception as exc:
        raise ValidationError(f"Failed to import '{path.name}': {exc}") from exc

    new_objects = [bpy.data.objects[name] for name in bpy.data.objects.keys() if name not in existing_objects]

    if not new_objects:
        return {
            "ok": True,
            "message": "Import completed but no new objects were created",
            "source_file": str(path),
            "imported_objects": [],
            "parent": None,
            "collection": target_coll.name if target_coll else None,
        }

    # If target collection is specified, move all imported objects there
    if target_coll:
        for obj in new_objects:
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            target_coll.objects.link(obj)

    # If parent_name is specified, create Chinese top-level parent Empty without altering children
    parent_obj = None
    if parent_name:
        parent_obj = bpy.data.objects.new(name=parent_name, object_data=None)
        parent_coll = target_coll or bpy.context.scene.collection
        parent_coll.objects.link(parent_obj)

        # Parent only root-level objects among the imported set
        for obj in new_objects:
            if obj.parent is None or obj.parent not in new_objects:
                obj.parent = parent_obj

    bpy.context.view_layer.update()

    all_materials = set()
    for obj in new_objects:
        for slot in obj.material_slots:
            if slot.material:
                all_materials.add(slot.material.name)

    return {
        "ok": True,
        "source_file": str(path),
        "object_count": len(new_objects),
        "imported_objects": [obj.name for obj in new_objects],
        "parent": parent_obj.name if parent_obj else None,
        "collection": target_coll.name if target_coll else None,
        "materials": sorted(all_materials),
        "format": ext.lstrip("."),
    }
