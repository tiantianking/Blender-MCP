from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))

from ai_previz_director.director.context import get_previz_state
from ai_previz_director.director.executor import execute_intent
from ai_previz_director.director.export import capture_clean_still
from ai_previz_director.director.semantic import tag_entity
from ai_previz_director.director.shot import create_shot, load_shots
from ai_previz_director.director.fcurves import action_fcurves

ARTIFACTS = ROOT / "tests" / "artifacts"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": str(detail)})
    if not ok:
        raise AssertionError(f"{name}: {detail}")


def setup_fixture():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end, scene.render.fps = 1, 48, 24
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 320, 180, 100
    for i in range(12):
        bpy.ops.mesh.primitive_cube_add(location=(i % 4 - 2, i // 4 + 2, 0))
        bpy.context.object.name = f"Background_{i:02d}"
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 1))
    actor = bpy.context.object
    actor.name = "Girl_Main"
    actor.scale = (0.35, 0.35, 1.0)
    tag_entity(actor, "ACTOR", "actor_girl_01", ["女孩", "女主", "girl", "woman"])
    actor.location.x = -1
    actor.keyframe_insert("location", frame=1)
    actor.location.x = 1
    actor.keyframe_insert("location", frame=25)
    bpy.ops.mesh.primitive_cube_add(location=(2, 0, 0.4), scale=(0.5, 0.5, 0.4))
    product = bpy.context.object
    product.name = "Earbud_Case"
    tag_entity(product, "PRODUCT", "product_earbud_case", ["耳机盒", "产品"])
    bpy.ops.object.camera_add(location=(0, -9, 3), rotation=(math.radians(72), 0, 0))
    cam = bpy.context.object
    cam.name = "CAM_S01"
    tag_entity(cam, "CAMERA", "camera_s01", ["当前摄影机"])
    scene.camera = cam
    from ai_previz_director.director.camera import look_at
    look_at(cam, actor)
    create_shot("S01", 1, 24, cam.name, "actor_girl_01", "MEDIUM")
    create_shot("S02", 25, 48, cam.name, "product_earbud_case", "WIDE")
    bpy.context.view_layer.objects.active = actor
    actor.select_set(True)
    return actor, product, cam


def run():
    actor, product, cam = setup_fixture()
    state = get_previz_state()
    record("TEST 1 context >10 objects", state["counts"]["scene_objects"] > 10 and len(state["actors"]) == 1 and len(state["products"]) == 1, state["counts"])

    result = execute_intent({"intent_version": 1, "operations": [{"type": "camera_set_lens", "target": "current_camera", "lens_mm": 55, "preserve_subject_framing": False}]}, "55mm")
    record("TEST 2 camera 55mm", result["ok"] and abs(cam.data.lens - 55) < 1e-6, cam.data.lens)

    actor_before = actor.matrix_world.copy()
    cam_before = cam.matrix_world.copy()
    result = execute_intent({"intent_version": 1, "operations": [{"type": "camera_orbit", "target": "current_camera", "subject": "actor_girl_01", "angle_degrees": -30}]}, "orbit right")
    record("TEST 3 camera-only orbit", actor.matrix_world == actor_before and cam.matrix_world != cam_before, result)

    action = actor.animation_data.action
    curves = action_fcurves(action, actor.animation_data.action_slot)
    old_frames = sorted({round(kp.co.x, 6) for fc in curves for kp in fc.keyframe_points})
    result = execute_intent({"intent_version": 1, "operations": [{"type": "actor_retime", "target": "actor_girl_01", "speed_factor": 0.7}]}, "slow actor")
    new_frames = sorted({round(kp.co.x, 6) for fc in curves for kp in fc.keyframe_points})
    expected_end = 1 + (25 - 1) / 0.7
    record("TEST 4 action retime 0.7", abs(new_frames[-1] - expected_end) < 1e-4 and new_frames[-1] > old_frames[-1], new_frames)

    result = execute_intent({"intent_version": 1, "operations": [{"type": "shot_product_closeup", "target": "product_earbud_case", "shot": "last", "hold_frames": 12}]}, "product closeup")
    record("TEST 5 last product closeup", load_shots()[-1]["shot_type"] == "PRODUCT_CLOSEUP" and load_shots()[-1]["frame_end"] == 60, load_shots()[-1])
    execute_intent({"intent_version": 1, "operations": [{"type": "previz_undo"}]}, "undo")
    record("TEST 6 undo", load_shots()[-1]["frame_end"] == 48, load_shots()[-1])
    execute_intent({"intent_version": 1, "operations": [{"type": "previz_redo"}]}, "redo")
    record("TEST 7 redo", load_shots()[-1]["frame_end"] == 60, load_shots()[-1])

    before_lens = cam.data.lens
    try:
        execute_intent({"intent_version": 1, "operations": [{"type": "camera_set_lens", "target": "current_camera", "lens_mm": 5000}]}, "invalid")
        invalid_rejected = False
    except Exception:
        invalid_rejected = True
    record("TEST 12 invalid intent is atomic", invalid_rejected and cam.data.lens == before_lens, cam.data.lens)

    still = capture_clean_still(str(ARTIFACTS / "clean_previz.png"))
    record("TEST 9/10 clean camera render", still["exists"] and os.path.getsize(still["path"]) > 0, still)
    fixture_path = ARTIFACTS / "mvp_fixture.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(fixture_path))
    record("fixture saved", fixture_path.exists(), fixture_path)
    (ARTIFACTS / "mvp_results.json").write_text(json.dumps(RESULTS, indent=2, ensure_ascii=False), encoding="utf-8")
    print("AI_PREVIZ_RESULTS", json.dumps(RESULTS, ensure_ascii=False))


try:
    run()
except Exception as exc:
    RESULTS.append({"name": "unhandled", "status": "FAIL", "detail": repr(exc)})
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "mvp_results.json").write_text(json.dumps(RESULTS, indent=2, ensure_ascii=False), encoding="utf-8")
    raise

