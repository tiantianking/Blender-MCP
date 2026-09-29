from __future__ import annotations


def action_fcurves(action, slot=None):
    """Return FCurves for legacy Actions and Blender 4.4+ layered Actions."""
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        return list(legacy)
    curves = []
    slot_handle = getattr(slot, "handle", None)
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            if getattr(strip, "type", None) != "KEYFRAME":
                continue
            for bag in getattr(strip, "channelbags", []):
                if slot_handle is None or getattr(getattr(bag, "slot", None), "handle", None) == slot_handle:
                    curves.extend(list(bag.fcurves))
    return curves

