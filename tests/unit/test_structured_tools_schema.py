from __future__ import annotations

import inspect
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from companion_mcp.server import mcp


def test_companion_mcp_tool_registration():
    # Verify all P0 and P1 tools are registered on FastMCP
    registered_tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}

    expected_tools = {
        "previz_get_state",
        "previz_set_frame",
        "previz_find_entity",
        "previz_tag_entity",
        "previz_get_scene_graph",
        "previz_set_object_transform",
        "previz_batch_transform",
        "previz_capture_views",
        "previz_set_viewport_view",
        "previz_collection_create",
        "previz_collection_move_objects",
        "previz_collection_set_visibility",
        "previz_duplicate_object",
        "previz_import_file",
        "previz_set_texture_tiling",
        "previz_get_task_status",
        "previz_undo",
        "previz_redo",
        "camera_set_lens",
        "camera_dolly",
        "camera_orbit",
        "camera_frame_subject",
        "camera_follow",
        "material_set_color",
        "actor_retime",
        "shot_product_closeup",
        "shot_create",
        "shot_set_camera",
        "previz_capture_view",
        "previz_export_clean",
        "previz_build_tracking_demo",
    }

    missing = expected_tools - set(registered_tools.keys())
    assert not missing, f"Missing MCP tools: {missing}"

    # Verify tool docstrings are descriptive and parameters match requirements
    scene_graph_fn = registered_tools["previz_get_scene_graph"].fn
    sig = inspect.signature(scene_graph_fn)
    assert "cursor" in sig.parameters
    assert "limit" in sig.parameters
    assert "collection" in sig.parameters
    assert "include_hidden" in sig.parameters
    assert "include_materials" in sig.parameters

    transform_fn = registered_tools["previz_set_object_transform"].fn
    tsig = inspect.signature(transform_fn)
    assert "reference" in tsig.parameters
    assert "mode" in tsig.parameters
    assert "space" in tsig.parameters
    assert "keyframe" in tsig.parameters
    assert "frame" in tsig.parameters

    views_fn = registered_tools["previz_capture_views"].fn
    vsig = inspect.signature(views_fn)
    assert "views" in vsig.parameters
    assert "camera" in vsig.parameters
    assert "output_dir" in vsig.parameters
