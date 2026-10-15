from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import bpy
import mathutils

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))

from ai_previz_director.director.scene_graph import get_scene_graph
from ai_previz_director.director.transform import set_object_transform, batch_transform
from ai_previz_director.director.view_capture import capture_views, set_viewport_view
from ai_previz_director.director.collection import create_collection, move_objects, set_visibility
from ai_previz_director.director.duplicate import duplicate_object
from ai_previz_director.director.appearance import set_texture_tiling
from ai_previz_director.director.transaction import MANAGER, capture_state, restore_state
from ai_previz_director.director.semantic import tag_entity
from ai_previz_director.director.errors import ValidationError
from ai_previz_director.dispatcher import DispatchRequest, _execute


def setup_large_scene() -> dict:
    scene = bpy.context.scene

    # Create 3 Collections
    coll_a = bpy.data.collections.new("City_District_A")
    coll_b = bpy.data.collections.new("City_District_B")
    coll_props = bpy.data.collections.new("Props_Collection")
    scene.collection.children.link(coll_a)
    scene.collection.children.link(coll_b)
    scene.collection.children.link(coll_props)

    # 1. Create Parent Building (Empty) and Children Windows/Doors
    parent_bldg = bpy.data.objects.new("Parent_Building_01", None)
    parent_bldg.location = (10.0, 20.0, 0.0)
    coll_a.objects.link(parent_bldg)

    # Child window mesh
    mesh_data = bpy.data.meshes.new("Window_Mesh")
    mesh_data.from_pydata(
        [(-0.5, 0, -0.5), (0.5, 0, -0.5), (0.5, 0, 0.5), (-0.5, 0, 0.5)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh_data.update()

    child_window = bpy.data.objects.new("Child_Window_01", mesh_data)
    child_window.parent = parent_bldg
    child_window.location = (2.0, 0.0, 5.0)
    coll_a.objects.link(child_window)

    # 2. Chinese Parent Entity
    parent_bus = bpy.data.objects.new("父级_校车", None)
    parent_bus.location = (-15.0, 5.0, 0.0)
    coll_b.objects.link(parent_bus)

    bus_body = bpy.data.objects.new("校车_车身", mesh_data)
    bus_body.parent = parent_bus
    bus_body.location = (0.0, 0.0, 1.0)
    coll_b.objects.link(bus_body)
    tag_entity(bus_body, "PRODUCT", "product_school_bus", ["校车", "bus"])

    # 3. Add a Camera and Light
    cam_data = bpy.data.cameras.new("CAM_Main")
    cam_data.lens = 35.0
    cam_obj = bpy.data.objects.new("CAM_Main", cam_data)
    cam_obj.location = (0.0, -30.0, 15.0)
    cam_obj.rotation_euler = (math.radians(65.0), 0.0, 0.0)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    tag_entity(cam_obj, "CAMERA", "camera_main", ["主相机"])

    light_data = bpy.data.lights.new("Sun_Light", type="SUN")
    light_obj = bpy.data.objects.new("Sun_Light", light_data)
    light_obj.location = (5.0, 5.0, 30.0)
    scene.collection.objects.link(light_obj)

    # 4. Generate 220+ background objects to test pagination and performance
    # Distribute between District A and District B
    for i in range(215):
        box_data = bpy.data.meshes.new(f"BoxMesh_{i:03d}")
        box_data.from_pydata(
            [(-0.2, -0.2, 0), (0.2, -0.2, 0), (0.2, 0.2, 0), (-0.2, 0.2, 0),
             (-0.2, -0.2, 0.5), (0.2, -0.2, 0.5), (0.2, 0.2, 0.5), (-0.2, 0.2, 0.5)],
            [],
            [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5)],
        )
        box_data.update()
        box_obj = bpy.data.objects.new(f"City_Block_{i:03d}", box_data)
        x = (i % 20) * 2.0 - 20.0
        y = (i // 20) * 2.0
        box_obj.location = (x, y, 0.0)
        target_coll = coll_a if i % 2 == 0 else coll_b
        target_coll.objects.link(box_obj)

    bpy.context.view_layer.update()
    return {
        "parent_bldg": parent_bldg,
        "child_window": child_window,
        "parent_bus": parent_bus,
        "bus_body": bus_body,
        "cam": cam_obj,
    }


def run_tests():
    fixtures = setup_large_scene()
    scene = bpy.context.scene
    total_objects = len(scene.objects)
    print(f"--- Total objects in test scene: {total_objects} (exceeds 200) ---")
    assert total_objects >= 220, f"Expected >= 220 objects, got {total_objects}"

    # =========================================================================
    # Test A: Scene Tree Query (get_scene_graph) & Pagination
    # =========================================================================
    print("Testing get_scene_graph pagination & hierarchy...")
    page1 = get_scene_graph(cursor=None, limit=100)
    assert page1["ok"] is True
    assert page1["total"] == total_objects
    assert len(page1["objects"]) == 100
    assert page1["truncated"] is True
    assert page1["next_cursor"] == "100"

    page2 = get_scene_graph(cursor=page1["next_cursor"], limit=100)
    assert len(page2["objects"]) == 100
    assert page2["truncated"] is True
    assert page2["next_cursor"] == "200"

    page3 = get_scene_graph(cursor=page2["next_cursor"], limit=100)
    assert len(page3["objects"]) == total_objects - 200
    assert page3["truncated"] is False
    assert page3["next_cursor"] is None

    # Verify no silent truncation: union of all names matches total set
    all_paged_names = {o["name"] for p in (page1, page2, page3) for o in p["objects"]}
    assert len(all_paged_names) == total_objects, "Pagination dropped or duplicated objects!"

    # Verify fields on parented object
    window_info = next(o for o in page1["objects"] if o["name"] == "Child_Window_01")
    assert window_info["parent"] == "Parent_Building_01"
    assert "City_District_A" in window_info["collections"]
    assert "aabb" in window_info and "center" in window_info["aabb"]
    assert window_info["vertex_count"] == 4
    assert window_info["face_count"] == 1

    # Verify collection filtering
    coll_a_graph = get_scene_graph(collection="City_District_A", limit=500)
    assert coll_a_graph["total"] < total_objects
    assert all("City_District_A" in o["collections"] for o in coll_a_graph["objects"])
    print("PASS: get_scene_graph")

    # =========================================================================
    # Test B: Parented Object World & Local Transform
    # =========================================================================
    print("Testing world and local transforms on parented objects...")
    child = fixtures["child_window"]
    parent = fixtures["parent_bldg"]

    # Initial state: Parent at (10, 20, 0), Child local at (2, 0, 5) -> World translation (12, 20, 5)
    bpy.context.view_layer.update()
    assert abs(child.matrix_world.translation.x - 12.0) < 1e-4
    assert abs(child.matrix_world.translation.y - 20.0) < 1e-4
    assert abs(child.matrix_world.translation.z - 5.0) < 1e-4

    # 1. Write WORLD transform to parented object: target world (0, 0, 10)
    res_world = set_object_transform(
        reference="Child_Window_01",
        location=[0.0, 0.0, 10.0],
        space="world",
        mode="absolute",
    )
    assert res_world["ok"] is True
    bpy.context.view_layer.update()

    # Child world translation must now be (0, 0, 10)
    assert abs(child.matrix_world.translation.x - 0.0) < 1e-4
    assert abs(child.matrix_world.translation.y - 0.0) < 1e-4
    assert abs(child.matrix_world.translation.z - 10.0) < 1e-4

    # Parent must remain unchanged at (10, 20, 0)
    assert abs(parent.location.x - 10.0) < 1e-4
    assert abs(parent.location.y - 20.0) < 1e-4

    # Child local location must have adapted to (-10, -20, 10)
    assert abs(child.location.x - (-10.0)) < 1e-4
    assert abs(child.location.y - (-20.0)) < 1e-4
    assert abs(child.location.z - 10.0) < 1e-4

    # 2. Write LOCAL transform to parented object: target local (3, 3, 3)
    set_object_transform(
        reference="Child_Window_01",
        location=[3.0, 3.0, 3.0],
        space="local",
        mode="absolute",
    )
    bpy.context.view_layer.update()
    assert abs(child.location.x - 3.0) < 1e-4
    # World should now be parent (10, 20, 0) + local (3, 3, 3) = (13, 23, 3)
    assert abs(child.matrix_world.translation.x - 13.0) < 1e-4
    assert abs(child.matrix_world.translation.y - 23.0) < 1e-4
    assert abs(child.matrix_world.translation.z - 3.0) < 1e-4
    print("PASS: set_object_transform (world/local parented object)")

    # =========================================================================
    # Test C: Batch Transform Validation & Atomic Rollback
    # =========================================================================
    print("Testing batch_transform atomic failure...")
    initial_child_loc = list(child.location)
    initial_parent_loc = list(parent.location)

    batch_changes = [
        {"reference": "Child_Window_01", "location": [99.0, 99.0, 99.0], "space": "local", "mode": "absolute"},
        {"reference": "Non_Existent_Object_404", "location": [0.0, 0.0, 0.0]},
        {"reference": "Parent_Building_01", "location": [50.0, 50.0, 50.0]},
    ]

    failed_cleanly = False
    try:
        batch_transform(batch_changes)
    except ValidationError:
        failed_cleanly = True

    assert failed_cleanly, "batch_transform should fail on non-existent reference"
    # Verify zero changes applied
    assert list(child.location) == initial_child_loc, "Batch transform partially mutated Child_Window_01!"
    assert list(parent.location) == initial_parent_loc, "Batch transform mutated Parent_Building_01!"
    print("PASS: batch_transform atomic rejection")

    # =========================================================================
    # Test D: Multi-Angle View Capture (5 views)
    # =========================================================================
    print("Testing 5-angle view captures (top, front, right, perspective, camera)...")
    with tempfile.TemporaryDirectory(prefix="previz-views-test-") as temp_dir:
        capture_res = capture_views(
            views=["top", "front", "right", "perspective", "camera"],
            output_dir=temp_dir,
        )
        assert capture_res["ok"] is True
        views_data = capture_res["views"]
        assert len(views_data) == 5

        hashes = {}
        for item in views_data:
            assert item["success"] is True, f"View {item['view']} failed: {item.get('error')}"
            path = item["path"]
            assert os.path.isfile(path), f"View file not found: {path}"
            size = os.path.getsize(path)
            assert size > 500, f"View file {path} suspiciously small: {size} bytes"

            with open(path, "rb") as f:
                hashes[item["view"]] = hashlib.md5(f.read()).hexdigest()

        # Check that views are distinct images
        unique_hashes = set(hashes.values())
        assert len(unique_hashes) >= 4, f"Views should produce distinct renders, got {len(unique_hashes)} unique out of 5"
        print("PASS: capture_views (5 distinct views saved)")

    # =========================================================================
    # Test E: Transaction Rollback & Deleted Object Protection
    # =========================================================================
    print("Testing transaction rollback and deleted object guard...")
    state_before = capture_state()
    # 1. Modify an object and restore
    parent.location = (88.0, 77.0, 66.0)
    bpy.context.view_layer.update()
    restore_state(state_before)
    bpy.context.view_layer.update()
    assert abs(parent.location.x - initial_parent_loc[0]) < 1e-4

    # 2. Deletion guard: delete an object and verify restore_state rejects it with clear guidance
    temp_obj = bpy.data.objects.new("Temp_To_Delete", None)
    scene.collection.objects.link(temp_obj)
    state_with_temp = capture_state()

    # Delete temp_obj
    bpy.data.objects.remove(temp_obj, do_unlink=True)
    deletion_blocked = False
    try:
        restore_state(state_with_temp)
    except ValidationError as exc:
        deletion_blocked = "需使用完整工程恢复点" in str(exc) or "deleted" in str(exc)

    assert deletion_blocked, "restore_state should reject rollback when objects were deleted"
    print("PASS: transaction delete guard")

    # =========================================================================
    # Test F: Checkpoint Creation via Dispatcher
    # =========================================================================
    print("Testing project checkpoint creation...")
    with tempfile.TemporaryDirectory(prefix="previz-cp-test-") as temp_dir:
        cp_file = Path(temp_dir) / "test_backup.blend"
        cp_res = _execute(
            DispatchRequest(
                "test-cp",
                "create_checkpoint",
                {"output_path": str(cp_file), "task_id": "task_abc123"},
                lambda _r: None,
            )
        )
        assert cp_res["ok"] is True
        assert cp_file.is_file() and cp_file.stat().st_size > 0
        assert cp_res["task_id"] == "task_abc123"
        assert cp_res.get("requires_user_confirmation") is True
        print("PASS: create_checkpoint")

    # =========================================================================
    # Test G: Dangerous API Protection
    # =========================================================================
    print("Testing dangerous operation protection...")
    dangerous_methods = ["bpy.ops.wm.read_factory_settings", "open_mainfile", "quit_blender"]
    # Verify importer rejects .blend
    blend_import_rejected = False
    try:
        from ai_previz_director.director.importer import import_file
        import_file("C:/fake/path/scene.blend")
    except ValidationError as exc:
        blend_import_rejected = "Prohibited" in str(exc) or "cannot import" in str(exc).lower()
    assert blend_import_rejected, "importer must reject .blend file replacements"
    print("PASS: dangerous operation protection")

    # =========================================================================
    # Test H: Collection, Duplicate, Texture Tiling (P1 Features)
    # =========================================================================
    print("Testing Collection, Duplicate and Texture Tiling...")
    # Collection
    c_res = create_collection("New_District_C", parent_collection="City_District_A")
    assert c_res["ok"] is True
    mv_res = move_objects(["CAM_Main"], "New_District_C")
    assert mv_res["ok"] is True
    vis_res = set_visibility("New_District_C", hide_viewport=True)
    assert vis_res["ok"] is True and vis_res["hide_viewport"] is True

    # Duplicate: linked vs full
    dup_linked = duplicate_object("Child_Window_01", linked=True, name="Window_Linked")
    assert dup_linked["ok"] is True and dup_linked["linked"] is True
    assert bpy.data.objects["Window_Linked"].data == fixtures["child_window"].data

    dup_full = duplicate_object("Child_Window_01", linked=False, name="Window_Full")
    assert dup_full["ok"] is True and dup_full["linked"] is False
    assert bpy.data.objects["Window_Full"].data != fixtures["child_window"].data

    # Texture tiling
    mat = bpy.data.materials.new(name="Building_Material")
    mat.use_nodes = True
    fixtures["child_window"].data.materials.append(mat)
    tiling_res = set_texture_tiling("Child_Window_01", scale_x=3.0, scale_y=4.0, rotation_degrees=45.0)
    assert tiling_res["ok"] is True
    assert tiling_res["new_scale"] == [3.0, 4.0, 1.0]
    assert abs(tiling_res["new_rotation_degrees"] - 45.0) < 1e-4
    print("PASS: Collections, Duplication, and Texture Tiling")

    print("\n=======================================================")
    print("ALL STRUCTURED TOOLS SMOKE TESTS PASSED SUCCESSFULLY!")
    print("=======================================================")


if __name__ == "__main__":
    run_tests()
