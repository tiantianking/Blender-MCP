from __future__ import annotations

import math
import os
import tempfile
import time
from pathlib import Path

import mathutils
import bpy

from .errors import ValidationError
from .semantic import find_entity


def _scene_bounds() -> tuple[mathutils.Vector, float]:
    scene = bpy.context.scene
    mesh_objs = [obj for obj in scene.objects if obj.type == "MESH" and obj.data and len(obj.data.vertices) > 0]
    if not mesh_objs:
        return mathutils.Vector((0.0, 0.0, 1.0)), 5.0

    all_corners = []
    for obj in mesh_objs:
        all_corners.extend([obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box])

    min_x = min(c.x for c in all_corners)
    max_x = max(c.x for c in all_corners)
    min_y = min(c.y for c in all_corners)
    max_y = max(c.y for c in all_corners)
    min_z = min(c.z for c in all_corners)
    max_z = max(c.z for c in all_corners)

    center = mathutils.Vector(((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (min_z + max_z) / 2.0))
    extent = max(max_x - min_x, max_y - min_y, max_z - min_z)
    radius = max(extent / 2.0, 1.0)
    return center, radius


def capture_views(
    views: list[str] | None = None,
    camera: str | None = None,
    output_dir: str | None = None,
) -> dict:
    if views is None:
        views = ["top", "front", "right", "perspective", "camera"]

    valid_views = {"top", "front", "right", "perspective", "camera"}
    for v in views:
        if v not in valid_views:
            raise ValidationError(f"Invalid view '{v}'. Must be one of: {sorted(valid_views)}")

    scene = bpy.context.scene
    if not output_dir:
        output_dir = str(Path(tempfile.gettempdir()) / f"previz_views_{int(time.time())}")
    os.makedirs(output_dir, exist_ok=True)

    # Save user's original scene and render settings
    orig_cam = scene.camera
    orig_filepath = scene.render.filepath
    orig_res_x = scene.render.resolution_x
    orig_res_y = scene.render.resolution_y
    orig_res_pct = scene.render.resolution_percentage
    orig_engine = scene.render.engine

    center, radius = _scene_bounds()
    distance = max(radius * 2.8, 6.0)

    temp_cam_data = bpy.data.cameras.new(name="_Previz_TempCamData_")
    temp_cam_data.lens = 50.0
    temp_cam_obj = bpy.data.objects.new(name="_Previz_TempCam_", object_data=temp_cam_data)
    scene.collection.objects.link(temp_cam_obj)

    # Configure clean preview render settings
    scene.render.resolution_x = 640
    scene.render.resolution_y = 360
    scene.render.resolution_percentage = 100
    scene.render.engine = "BLENDER_WORKBENCH"

    results = []
    try:
        for view_name in views:
            out_file = os.path.join(output_dir, f"view_{view_name}.png")
            active_render_cam = temp_cam_obj

            if view_name == "top":
                pos = center + mathutils.Vector((0.0, 0.0, distance))
                temp_cam_obj.location = pos
                temp_cam_obj.rotation_euler = mathutils.Euler((0.0, 0.0, 0.0))
            elif view_name == "front":
                pos = center + mathutils.Vector((0.0, -distance, 0.0))
                temp_cam_obj.location = pos
                temp_cam_obj.rotation_euler = mathutils.Euler((math.radians(90.0), 0.0, 0.0))
            elif view_name == "right":
                pos = center + mathutils.Vector((distance, 0.0, 0.0))
                temp_cam_obj.location = pos
                temp_cam_obj.rotation_euler = mathutils.Euler((math.radians(90.0), 0.0, math.radians(90.0)))
            elif view_name == "perspective":
                pos = center + mathutils.Vector((distance * 0.7, -distance * 0.7, distance * 0.5))
                temp_cam_obj.location = pos
                dir_vec = (center - pos).normalized()
                temp_cam_obj.rotation_euler = dir_vec.to_track_quat("-Z", "Y").to_euler()
            elif view_name == "camera":
                target_cam = None
                if camera:
                    target_cam = bpy.data.objects.get(camera)
                    if not target_cam or target_cam.type != "CAMERA":
                        try:
                            target_cam = find_entity(camera, {"CAMERA"})
                        except Exception:
                            target_cam = None
                if not target_cam:
                    target_cam = orig_cam
                if not target_cam:
                    results.append({
                        "view": view_name,
                        "path": None,
                        "camera": None,
                        "matrix": None,
                        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
                        "success": False,
                        "error": "No camera found in scene and no valid camera specified",
                    })
                    continue
                active_render_cam = target_cam

            scene.camera = active_render_cam
            scene.render.filepath = out_file
            bpy.context.view_layer.update()

            try:
                bpy.ops.render.render(write_still=True)
                cam_matrix = [list(row) for row in active_render_cam.matrix_world]
                results.append({
                    "view": view_name,
                    "path": out_file,
                    "camera": active_render_cam.name,
                    "matrix": cam_matrix,
                    "resolution": [scene.render.resolution_x, scene.render.resolution_y],
                    "success": True,
                    "error": None,
                })
            except Exception as exc:
                results.append({
                    "view": view_name,
                    "path": out_file,
                    "camera": active_render_cam.name,
                    "matrix": None,
                    "resolution": [scene.render.resolution_x, scene.render.resolution_y],
                    "success": False,
                    "error": str(exc),
                })
    finally:
        # Non-destructive restoration of user scene
        if temp_cam_obj.name in scene.collection.objects:
            scene.collection.objects.unlink(temp_cam_obj)
        if temp_cam_obj.name in bpy.data.objects:
            bpy.data.objects.remove(temp_cam_obj, do_unlink=True)
        if temp_cam_data.name in bpy.data.cameras:
            bpy.data.cameras.remove(temp_cam_data, do_unlink=True)

        scene.camera = orig_cam
        scene.render.filepath = orig_filepath
        scene.render.resolution_x = orig_res_x
        scene.render.resolution_y = orig_res_y
        scene.render.resolution_percentage = orig_res_pct
        scene.render.engine = orig_engine
        bpy.context.view_layer.update()

    return {"ok": True, "output_dir": output_dir, "views": results}


def set_viewport_view(view: str, camera: str | None = None) -> dict:
    valid_views = {"top", "front", "right", "perspective", "camera"}
    if view not in valid_views:
        raise ValidationError(f"Invalid view '{view}'. Must be one of: {sorted(valid_views)}")

    scene = bpy.context.scene
    center, radius = _scene_bounds()
    distance = max(radius * 2.8, 6.0)

    # If GUI screen area is available, adjust view3d
    has_gui = False
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager and getattr(bpy.context, "screen", None):
        for area in bpy.context.screen.areas:
            if area.type == "VIEW_3D":
                has_gui = True
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        r3d = space.region_3d
                        if view == "camera":
                            r3d.view_perspective = "CAMERA"
                        else:
                            r3d.view_perspective = "PERSP"
                            if view == "top":
                                r3d.view_rotation = mathutils.Euler((0.0, 0.0, 0.0)).to_quaternion()
                            elif view == "front":
                                r3d.view_rotation = mathutils.Euler((math.radians(90.0), 0.0, 0.0)).to_quaternion()
                            elif view == "right":
                                r3d.view_rotation = mathutils.Euler((math.radians(90.0), 0.0, math.radians(90.0))).to_quaternion()
                            elif view == "perspective":
                                dir_vec = mathutils.Vector((-0.7, 0.7, -0.5)).normalized()
                                r3d.view_rotation = dir_vec.to_track_quat("-Z", "Y")

    if view == "camera":
        target = bpy.data.objects.get(camera) if camera else scene.camera
        if target and target.type == "CAMERA":
            scene.camera = target

    return {
        "ok": True,
        "view": view,
        "active_camera": scene.camera.name if scene.camera else None,
        "viewport_gui_adjusted": has_gui,
    }
