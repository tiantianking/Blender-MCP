from __future__ import annotations

import queue
from dataclasses import dataclass
from typing import Callable

from .director.executor import execute_intent
from .director.context import get_previz_state
from .director.export import capture_clean_still, export_clean_video
from .director.semantic import entity_summary, find_entity, tag_entity
from .director.demo import build_tracking_demo


@dataclass
class DispatchRequest:
    request_id: str
    method: str
    payload: dict
    callback: Callable[[dict], None]


REQUESTS: queue.Queue[DispatchRequest] = queue.Queue()


def submit(request: DispatchRequest) -> None:
    REQUESTS.put(request)


def _execute(request: DispatchRequest) -> dict:
    p = request.payload
    if request.method == "execute_intent":
        return execute_intent(p["intent"], p.get("prompt", ""))
    if request.method == "get_state":
        return {"ok": True, "state": get_previz_state(p.get("detail_ids"))}
    if request.method == "find_entity":
        return {"ok": True, "entity": entity_summary(find_entity(p["reference"]))}
    if request.method == "tag_entity":
        obj = find_entity(p["reference"])
        return {"ok": True, "entity": tag_entity(obj, p["role"], p["entity_id"], p.get("aliases", []))}
    if request.method == "capture_view":
        return {"ok": True, "result": capture_clean_still(p["output_path"])}
    if request.method == "export_clean":
        return {"ok": True, "result": export_clean_video(p["output_path"], p.get("frame_start"), p.get("frame_end"))}
    if request.method == "build_tracking_demo":
        return {"ok": True, "result": build_tracking_demo(p["output_path"])}
    if request.method == "set_frame":
        import bpy
        bpy.context.scene.frame_set(int(p["frame"]))
        return {"ok": True, "frame": bpy.context.scene.frame_current, "state": get_previz_state()}
    return {"ok": False, "error": f"Unknown method: {request.method}"}


def poll() -> float:
    try:
        request = REQUESTS.get_nowait()
    except queue.Empty:
        return 0.1
    try:
        response = _execute(request)
    except Exception as exc:
        response = {"ok": False, "error": str(exc), "error_type": type(exc).__name__}
    request.callback(response)
    return 0.05

