from __future__ import annotations

from .errors import ValidationError

ALLOWED = {
    "camera_set_lens": ({"target", "lens_mm", "subject", "preserve_subject_framing"}, {"lens_mm"}),
    "camera_dolly": ({"target", "distance"}, {"distance"}),
    "camera_orbit": ({"target", "subject", "angle_degrees"}, {"subject", "angle_degrees"}),
    "camera_look_at": ({"target", "subject"}, {"subject"}),
    "camera_frame_subject": ({"target", "subject", "padding"}, {"subject"}),
    "actor_retime": ({"target", "speed_factor", "frame_start", "frame_end"}, {"target", "speed_factor"}),
    "animation_shift": ({"target", "frame_delta", "frame_start", "frame_end"}, {"target", "frame_delta"}),
    "animation_scale_time": ({"target", "time_scale", "frame_start", "frame_end"}, {"target", "time_scale"}),
    "animation_insert_hold": ({"target", "frame_end", "hold_frames"}, {"target", "frame_end", "hold_frames"}),
    "shot_create": ({"shot_id", "frame_start", "frame_end", "target", "subject", "shot_type"}, {"shot_id", "frame_start", "frame_end"}),
    "shot_set_range": ({"shot", "frame_start", "frame_end"}, {"shot", "frame_start", "frame_end"}),
    "shot_set_camera": ({"shot", "target"}, {"shot", "target"}),
    "shot_product_closeup": ({"shot", "target", "hold_frames", "padding"}, {"target"}),
    "shot_actor_closeup": ({"shot", "target", "hold_frames", "padding"}, {"target"}),
    "shot_hold": ({"shot", "hold_frames"}, {"hold_frames"}),
    "previz_undo": (set(), set()),
    "previz_redo": (set(), set()),
}


def validate_intent(intent: dict) -> dict:
    if not isinstance(intent, dict) or intent.get("intent_version") != 1:
        raise ValidationError("intent_version must equal 1")
    operations = intent.get("operations")
    if not isinstance(operations, list) or not 1 <= len(operations) <= 8:
        raise ValidationError("operations must contain 1 to 8 items")
    for index, op in enumerate(operations):
        if not isinstance(op, dict):
            raise ValidationError(f"operation {index} must be an object")
        op_type = op.get("type")
        if op_type not in ALLOWED:
            raise ValidationError(f"operation {index} has unsupported type: {op_type}")
        allowed, required = ALLOWED[op_type]
        extra = set(op) - allowed - {"type"}
        missing = required - set(op)
        if extra:
            raise ValidationError(f"operation {index} has unexpected fields: {sorted(extra)}")
        if missing:
            raise ValidationError(f"operation {index} is missing fields: {sorted(missing)}")
        _validate_values(index, op)
    if len(operations) > 1 and any(op["type"] in {"previz_undo", "previz_redo"} for op in operations):
        raise ValidationError("undo/redo must be the only operation")
    return intent


def _validate_values(index: int, op: dict) -> None:
    def number(name, low=None, high=None):
        if name not in op:
            return
        value = op[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(f"operation {index}.{name} must be numeric")
        if low is not None and value < low or high is not None and value > high:
            raise ValidationError(f"operation {index}.{name} is outside [{low}, {high}]")

    number("lens_mm", 8, 600)
    number("distance", -10000, 10000)
    number("angle_degrees", -360, 360)
    number("speed_factor", 0.05, 10)
    number("time_scale", 0.05, 20)
    number("padding", 0.01, 2)
    number("hold_frames", 1, 10000)
    if "frame_start" in op and "frame_end" in op and op["frame_end"] < op["frame_start"]:
        raise ValidationError(f"operation {index} frame_end precedes frame_start")

