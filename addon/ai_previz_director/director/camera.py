from __future__ import annotations

import math

import bpy
from mathutils import Vector, Matrix

from .errors import ValidationError
from .semantic import find_entity


def _camera(reference: str | None) -> bpy.types.Object:
    obj = find_entity(reference or "current_camera", {"CAMERA"})
    if obj.type != "CAMERA":
        raise ValidationError(f"Not a camera: {obj.name}")
    return obj


def _world_bounds(obj: bpy.types.Object) -> list[Vector]:
    if obj.bound_box:
        return [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return [obj.matrix_world.translation.copy()]


def subject_center(obj: bpy.types.Object) -> Vector:
    pts = _world_bounds(obj)
    return sum(pts, Vector()) / len(pts)


def look_at(camera: bpy.types.Object, subject: bpy.types.Object) -> None:
    direction = subject_center(subject) - camera.location
    if direction.length < 1e-6:
        raise ValidationError("Camera and subject occupy the same point")
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def set_lens(reference: str | None, lens_mm: float, subject_ref: str | None = None, preserve_framing: bool = False) -> dict:
    camera = _camera(reference)
    old_lens = float(camera.data.lens)
    subject = find_entity(subject_ref) if subject_ref else None
    if preserve_framing and subject:
        center = subject_center(subject)
        offset = camera.location - center
        if offset.length > 1e-6:
            camera.location = center + offset * (float(lens_mm) / old_lens)
    camera.data.lens = float(lens_mm)
    if subject:
        look_at(camera, subject)
    return {"camera": camera.name, "lens_before": old_lens, "lens_after": camera.data.lens}


def dolly(reference: str | None, distance: float) -> dict:
    camera = _camera(reference)
    before = camera.location.copy()
    forward = camera.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))
    camera.location += forward * float(distance)
    return {"camera": camera.name, "location_before": list(before), "location_after": list(camera.location)}


def orbit(reference: str | None, subject_ref: str, angle_degrees: float) -> dict:
    camera = _camera(reference)
    subject = find_entity(subject_ref)
    center = subject_center(subject)
    offset = camera.location - center
    rotation = Matrix.Rotation(math.radians(float(angle_degrees)), 4, "Z")
    before = camera.location.copy()
    camera.location = center + rotation @ offset
    look_at(camera, subject)
    return {"camera": camera.name, "subject": subject.name, "angle_degrees": angle_degrees, "location_before": list(before), "location_after": list(camera.location)}


def frame_subject(reference: str | None, subject_ref: str, padding: float = 0.15) -> dict:
    camera = _camera(reference)
    subject = find_entity(subject_ref)
    pts = _world_bounds(subject)
    center = sum(pts, Vector()) / len(pts)
    radius = max((p - center).length for p in pts) or 0.5
    # Use the narrower of horizontal/vertical FOV so wide subjects still fit
    # when the render aspect is portrait or the sensor is vertical.
    fov_y = camera.data.angle_y
    fov_x = camera.data.angle_x
    if fov_y > 1e-6 and fov_x > 1e-6:
        fov = min(fov_x, fov_y)
    elif fov_y > 1e-6:
        fov = fov_y
    else:
        fov = math.radians(35)
    distance = radius * (1.0 + float(padding)) / math.tan(fov / 2.0)
    backward = camera.matrix_world.to_quaternion() @ Vector((0.0, 0.0, 1.0))
    camera.location = center + backward.normalized() * distance
    look_at(camera, subject)
    return {"camera": camera.name, "subject": subject.name, "distance": distance, "padding": padding}


def follow(reference: str | None, subject_ref: str, offset=(0.0, -6.0, 3.0)) -> dict:
    camera = _camera(reference)
    subject = find_entity(subject_ref)
    focus_target = bpy.data.objects.get(str(subject.get("previz_focus_object", ""))) or subject
    for constraint in list(camera.constraints):
        if constraint.name.startswith("AI_PREVIZ_FOLLOW_"):
            camera.constraints.remove(constraint)
    camera.location = Vector(tuple(float(value) for value in offset))
    copy_location = camera.constraints.new("COPY_LOCATION")
    copy_location.name = "AI_PREVIZ_FOLLOW_LOCATION"
    copy_location.target = subject
    copy_location.use_offset = True
    track = camera.constraints.new("TRACK_TO")
    track.name = "AI_PREVIZ_FOLLOW_TRACK"
    track.target = focus_target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    bpy.context.view_layer.update()
    return {
        "camera": camera.name,
        "subject": subject.name,
        "focus_target": focus_target.name,
        "offset": [float(value) for value in offset],
        "constraints": [copy_location.name, track.name],
    }

