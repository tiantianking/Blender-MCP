import math

import bpy

from .shot import load_shots


def validate_scene() -> dict:
    errors = []
    scene = bpy.context.scene
    if scene.frame_end < scene.frame_start:
        errors.append("Scene frame range is inverted")
    for camera in (o for o in scene.objects if o.type == "CAMERA"):
        values = [*camera.location, *camera.rotation_euler, camera.data.lens]
        if not all(math.isfinite(float(v)) for v in values):
            errors.append(f"Camera contains non-finite values: {camera.name}")
        if not 1 <= camera.data.lens <= 1000:
            errors.append(f"Camera lens is invalid: {camera.name}={camera.data.lens}")
    for shot in load_shots():
        if int(shot.get("frame_end", -1)) < int(shot.get("frame_start", 0)):
            errors.append(f"Shot range is invalid: {shot.get('shot_id')}")
        camera_name = shot.get("camera")
        if camera_name and not bpy.data.objects.get(camera_name):
            errors.append(f"Shot camera is missing: {camera_name}")
    return {"ok": not errors, "errors": errors}

