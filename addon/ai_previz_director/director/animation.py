from __future__ import annotations

import bpy

from .errors import UnsupportedFeature, ValidationError
from .semantic import find_entity
from .fcurves import action_fcurves


def _action_for(reference: str):
    obj = find_entity(reference)
    ad = obj.animation_data
    action = ad.action if ad else None
    if not action:
        raise UnsupportedFeature(f"{obj.name} has no active Action")
    if action.users > 1:
        raise UnsupportedFeature(f"Shared Action is not supported in MVP: {action.name}")
    if ad.nla_tracks and any(track.strips for track in ad.nla_tracks):
        raise UnsupportedFeature(f"NLA animation is not supported in MVP: {obj.name}")
    if getattr(ad, "drivers", None) and len(ad.drivers):
        raise UnsupportedFeature(f"Driver-heavy animation is not supported in MVP: {action.name}")
    return obj, action, action_fcurves(action, getattr(ad, "action_slot", None))


def _points(curves, frame_start=None, frame_end=None):
    for fcurve in curves:
        for point in fcurve.keyframe_points:
            frame = float(point.co.x)
            if frame_start is not None and frame < frame_start:
                continue
            if frame_end is not None and frame > frame_end:
                continue
            yield fcurve, point


def shift(reference: str, frame_delta: float, frame_start=None, frame_end=None) -> dict:
    obj, action, curves = _action_for(reference)
    count = 0
    for _, point in _points(curves, frame_start, frame_end):
        point.co.x += frame_delta
        point.handle_left.x += frame_delta
        point.handle_right.x += frame_delta
        count += 1
    for fc in curves:
        fc.update()
    return {"object": obj.name, "action": action.name, "shifted_keyframes": count, "frame_delta": frame_delta}


def scale_time(reference: str, time_scale: float, frame_start=None, frame_end=None) -> dict:
    if time_scale <= 0:
        raise ValidationError("time_scale must be positive")
    obj, action, curves = _action_for(reference)
    selected = list(_points(curves, frame_start, frame_end))
    if not selected:
        raise ValidationError("No keyframes in requested range")
    pivot = float(frame_start) if frame_start is not None else min(p.co.x for _, p in selected)
    for _, point in selected:
        point.co.x = pivot + (point.co.x - pivot) * time_scale
        point.handle_left.x = pivot + (point.handle_left.x - pivot) * time_scale
        point.handle_right.x = pivot + (point.handle_right.x - pivot) * time_scale
    for fc in curves:
        fc.update()
    return {"object": obj.name, "action": action.name, "scaled_keyframes": len(selected), "time_scale": time_scale, "pivot": pivot}


def retime_speed(reference: str, speed_factor: float, frame_start=None, frame_end=None) -> dict:
    if speed_factor <= 0:
        raise ValidationError("speed_factor must be positive")
    result = scale_time(reference, 1.0 / float(speed_factor), frame_start, frame_end)
    result["speed_factor"] = speed_factor
    return result


def insert_hold(reference: str, frame_end: int, hold_frames: int) -> dict:
    obj, action, curves = _action_for(reference)
    if hold_frames <= 0:
        raise ValidationError("hold_frames must be positive")
    shifted = 0
    for _, point in _points(curves):
        if point.co.x > frame_end:
            point.co.x += hold_frames
            point.handle_left.x += hold_frames
            point.handle_right.x += hold_frames
            shifted += 1
    inserted = 0
    for fc in curves:
        value = fc.evaluate(frame_end)
        fc.keyframe_points.insert(frame_end, value, options={"FAST"})
        fc.keyframe_points.insert(frame_end + hold_frames, value, options={"FAST"})
        fc.update()
        inserted += 2
    return {"object": obj.name, "action": action.name, "hold_frames": hold_frames, "inserted_keyframes": inserted, "shifted_keyframes": shifted}

