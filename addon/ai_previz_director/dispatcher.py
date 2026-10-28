from __future__ import annotations

import queue
import os
from dataclasses import dataclass
from typing import Callable

from .director.executor import execute_intent
from .director.context import get_previz_state
from .director.export import capture_clean_still, export_clean_video
from .director.semantic import entity_summary, find_entity, tag_entity
from .director.demo import build_tracking_demo
from .director.scene_graph import get_scene_graph
from .director.transform import set_object_transform, batch_transform
from .director.primitives import rename_object, VALID_PRIMITIVES
from .director.view_capture import capture_views, set_viewport_view
from .director.collection import create_collection, move_objects, set_visibility
from .director.duplicate import duplicate_object
from .director.importer import import_file
from .director.appearance import set_texture_tiling
from .director.tasks import TASKS


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
    if request.method == "get_scene_graph":
        return get_scene_graph(
            cursor=p.get("cursor"),
            limit=p.get("limit", 200),
            collection=p.get("collection"),
            include_hidden=p.get("include_hidden", True),
            include_materials=p.get("include_materials", False),
            include_matrix=p.get("include_matrix", False),
        )
    if request.method == "set_object_transform":
        return set_object_transform(
            reference=p["reference"],
            location=p.get("location"),
            rotation=p.get("rotation"),
            scale=p.get("scale"),
            mode=p.get("mode", "absolute"),
            space=p.get("space", "world"),
            keyframe=p.get("keyframe", False),
            frame=p.get("frame"),
        )
    if request.method == "batch_transform":
        return batch_transform(p.get("changes", []))
    if request.method == "rename_entity":
        return rename_object(reference=p["reference"], new_name=p["new_name"])
    if request.method == "list_primitives":
        return {"ok": True, "primitives": sorted(VALID_PRIMITIVES)}
    if request.method == "capture_views":
        return capture_views(
            views=p.get("views"),
            camera=p.get("camera"),
            output_dir=p.get("output_dir"),
        )
    if request.method == "set_viewport_view":
        return set_viewport_view(view=p["view"], camera=p.get("camera"))
    if request.method == "collection_create":
        return create_collection(name=p["name"], parent_collection=p.get("parent_collection"))
    if request.method == "collection_move_objects":
        return move_objects(objects=p["objects"], target_collection=p["target_collection"])
    if request.method == "collection_set_visibility":
        return set_visibility(
            collection=p["collection"],
            hide_viewport=p.get("hide_viewport"),
            hide_render=p.get("hide_render"),
        )
    if request.method == "duplicate_object":
        return duplicate_object(
            reference=p["reference"],
            linked=p.get("linked", False),
            name=p.get("name"),
            collection=p.get("collection"),
        )
    if request.method == "import_file":
        return import_file(
            filepath=p["filepath"],
            collection=p.get("collection"),
            parent_name=p.get("parent_name"),
        )
    if request.method == "set_texture_tiling":
        return set_texture_tiling(
            target=p["target"],
            scale_x=p["scale_x"],
            scale_y=p["scale_y"],
            rotation_degrees=p.get("rotation_degrees", 0.0),
            mapping_mode=p.get("mapping_mode", "POINT"),
            material_slot=p.get("material_slot", 0),
        )
    if request.method == "get_task_status":
        return TASKS.get_task(p["task_id"])
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
    if request.method == "create_checkpoint":
        import bpy
        output_path = os.path.abspath(p["output_path"])
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        original_path = bpy.data.filepath
        bpy.ops.wm.save_as_mainfile(filepath=output_path, copy=True, check_existing=False)
        return {
            "ok": True,
            "checkpoint": output_path,
            "source_file": original_path,
            "current_file": bpy.data.filepath,
            "task_id": p.get("task_id", ""),
            "requires_user_confirmation": True,
            "message": "完整工程检查点已生成。恢复属于高影响操作，必须由用户明确确认，禁止 Agent 静默重载工程。",
        }
    if request.method == "ensure_blender_mcp":
        import bpy
        if "blender_mcp" not in bpy.context.preferences.addons:
            bpy.ops.preferences.addon_enable(module="blender_mcp")
        server = getattr(bpy.types, "blendermcp_server", None)
        if not server or not getattr(server, "running", False):
            bpy.ops.blendermcp.start_server()
            server = getattr(bpy.types, "blendermcp_server", None)
        running = bool(server and getattr(server, "running", False))
        return {
            "ok": running,
            "running": running,
            "port": int(getattr(bpy.context.scene, "blendermcp_port", 9876)),
            "error": "Blender MCP server could not be started" if not running else "",
        }
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
