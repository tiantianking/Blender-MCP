from __future__ import annotations

import bpy

from .errors import UnsupportedFeature, ValidationError
from .semantic import find_entity, resolve_object


def _meshes(root: bpy.types.Object) -> list[bpy.types.Object]:
    objects = [root, *root.children_recursive]
    return [obj for obj in objects if obj.type == "MESH"]


def set_color(reference: str, red: float, green: float, blue: float) -> dict:
    rgb = tuple(float(value) for value in (red, green, blue))
    if any(value < 0.0 or value > 1.0 for value in rgb):
        raise ValidationError("Color channels must be between 0 and 1")
    root = find_entity(reference)
    meshes = _meshes(root)
    if not meshes:
        raise UnsupportedFeature(f"{root.name} has no mesh objects")
    materials = []
    for obj in meshes:
        for slot in obj.material_slots:
            material = slot.material
            if material and material.name not in materials:
                materials.append(material.name)
                alpha = float(material.diffuse_color[3])
                material.diffuse_color = (*rgb, alpha)
                if material.use_nodes and material.node_tree:
                    principled = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
                    if principled and "Base Color" in principled.inputs:
                        node_alpha = float(principled.inputs["Base Color"].default_value[3])
                        principled.inputs["Base Color"].default_value = (*rgb, node_alpha)
    if not materials:
        raise UnsupportedFeature(f"{root.name} has no editable material")
    return {"object": root.name, "rgb": list(rgb), "materials": materials, "mesh_count": len(meshes)}


def set_texture_tiling(
    target: str,
    scale_x: float,
    scale_y: float,
    rotation_degrees: float = 0.0,
    mapping_mode: str = "POINT",
    material_slot: int = 0,
) -> dict:
    import math

    root = resolve_object(target)

    meshes = _meshes(root) if root.type != "MESH" else [root]
    if not meshes:
        raise ValidationError(f"Object '{root.name}' contains no mesh components")

    target_mesh = meshes[0]
    if not target_mesh.material_slots or len(target_mesh.material_slots) <= material_slot:
        raise ValidationError(f"Object '{target_mesh.name}' has no material at slot {material_slot}")

    slot = target_mesh.material_slots[material_slot]
    material = slot.material
    if not material:
        raise ValidationError(f"Material slot {material_slot} on '{target_mesh.name}' is empty")

    if not material.use_nodes or not material.node_tree:
        material.use_nodes = True

    nodes = material.node_tree.nodes
    links = material.node_tree.links

    mapping_node = next((n for n in nodes if n.type == "MAPPING"), None)
    tex_node = next((n for n in nodes if n.type == "TEX_IMAGE"), None)
    principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)

    if mapping_node:
        old_scale = [float(v) for v in mapping_node.inputs["Scale"].default_value]
        old_rot = [float(v) for v in mapping_node.inputs["Rotation"].default_value]
        mapping_node.inputs["Scale"].default_value = (float(scale_x), float(scale_y), 1.0)
        mapping_node.inputs["Rotation"].default_value[2] = math.radians(float(rotation_degrees))
        if hasattr(mapping_node, "vector_type") and mapping_mode in {"POINT", "TEXTURE", "VECTOR", "NORMAL"}:
            mapping_node.vector_type = mapping_mode
    elif tex_node or principled:
        ref_node = tex_node or principled
        old_scale = [1.0, 1.0, 1.0]
        old_rot = [0.0, 0.0, 0.0]
        mapping_node = nodes.new(type="ShaderNodeMapping")
        mapping_node.inputs["Scale"].default_value = (float(scale_x), float(scale_y), 1.0)
        mapping_node.inputs["Rotation"].default_value[2] = math.radians(float(rotation_degrees))
        if hasattr(mapping_node, "vector_type") and mapping_mode in {"POINT", "TEXTURE", "VECTOR", "NORMAL"}:
            mapping_node.vector_type = mapping_mode

        tex_coord = next((n for n in nodes if n.type == "TEX_COORD"), None)
        if not tex_coord:
            tex_coord = nodes.new(type="ShaderNodeTexCoord")
            tex_coord.location = (ref_node.location.x - 500, ref_node.location.y)
        mapping_node.location = (ref_node.location.x - 250, ref_node.location.y)

        # Link UV or Generated -> Mapping
        output_socket = tex_coord.outputs.get("UV") or tex_coord.outputs.get("Generated")
        if output_socket and "Vector" in mapping_node.inputs:
            links.new(output_socket, mapping_node.inputs["Vector"])
        if tex_node and "Vector" in tex_node.inputs:
            links.new(mapping_node.outputs["Vector"], tex_node.inputs["Vector"])
    else:
        raise ValidationError(f"Material '{material.name}' has no Principled BSDF, Image Texture, or Mapping node")

    return {
        "ok": True,
        "target": root.name,
        "material": material.name,
        "slot": material_slot,
        "mapping_node": mapping_node.name,
        "old_scale": old_scale,
        "new_scale": [float(scale_x), float(scale_y), 1.0],
        "old_rotation_degrees": [math.degrees(v) for v in old_rot],
        "new_rotation_degrees": float(rotation_degrees),
        "mapping_mode": getattr(mapping_node, "vector_type", mapping_mode),
    }
