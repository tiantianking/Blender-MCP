import json
import re
from typing import Iterable

import bpy

from .errors import AmbiguousEntity, EntityNotFound, ValidationError

ROLES = {"ACTOR", "PRODUCT", "CAMERA", "PROP", "CROWD", "BACKGROUND", "LIGHT"}


def _aliases(obj: bpy.types.Object) -> list[str]:
    raw = obj.get("previz_aliases", "[]")
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw]
    try:
        value = json.loads(raw)
        return [str(x) for x in value] if isinstance(value, list) else []
    except (TypeError, ValueError):
        return [x.strip() for x in str(raw).split(",") if x.strip()]


def tag_entity(obj: bpy.types.Object, role: str, entity_id: str, aliases: Iterable[str] = ()) -> dict:
    role = role.upper().strip()
    if role not in ROLES:
        raise ValidationError(f"Unsupported semantic role: {role}")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", entity_id):
        raise ValidationError("previz_id must contain only letters, digits, underscore or hyphen")
    obj["previz_role"] = role
    obj["previz_id"] = entity_id
    obj["previz_aliases"] = json.dumps(sorted({str(a).strip() for a in aliases if str(a).strip()}), ensure_ascii=False)
    if role == "ACTOR":
        obj["previz_actor_id"] = entity_id
    elif role == "PRODUCT":
        obj["previz_product_id"] = entity_id
    return entity_summary(obj)


def auto_role(obj: bpy.types.Object) -> str | None:
    explicit = str(obj.get("previz_role", "")).upper()
    if explicit in ROLES:
        return explicit
    if obj.type == "CAMERA":
        return "CAMERA"
    if obj.type == "LIGHT":
        return "LIGHT"
    if obj.type == "ARMATURE":
        return "ACTOR"
    return None


def entity_id(obj: bpy.types.Object) -> str:
    return str(obj.get("previz_id") or obj.get("previz_actor_id") or obj.get("previz_product_id") or obj.name)


def entity_summary(obj: bpy.types.Object) -> dict:
    return {
        "id": entity_id(obj),
        "name": obj.name,
        "role": auto_role(obj),
        "aliases": _aliases(obj),
        "type": obj.type,
    }


def semantic_objects() -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if auto_role(obj)]


def find_entity(reference: str | None, roles: set[str] | None = None) -> bpy.types.Object:
    if not reference:
        raise EntityNotFound("No entity reference supplied")
    ref = reference.strip().casefold()
    scene = bpy.context.scene
    if ref in {"current_camera", "当前摄影机", "当前相机"}:
        if scene.camera and (not roles or "CAMERA" in roles):
            return scene.camera
        raise EntityNotFound("Scene has no active camera")
    if ref in {"active_object", "当前对象"} and bpy.context.view_layer.objects.active:
        obj = bpy.context.view_layer.objects.active
        if not roles or auto_role(obj) in roles:
            return obj
    candidates = []
    for obj in scene.objects:
        role = auto_role(obj)
        if roles and role not in roles:
            continue
        keys = {obj.name.casefold(), entity_id(obj).casefold(), *(a.casefold() for a in _aliases(obj))}
        if ref in keys:
            candidates.append(obj)
    if not candidates:
        raise EntityNotFound(f"Entity not found: {reference}")
    if len(candidates) > 1:
        raise AmbiguousEntity(f"Ambiguous entity '{reference}': {[o.name for o in candidates]}")
    return candidates[0]

