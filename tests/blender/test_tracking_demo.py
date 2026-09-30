from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))

from ai_previz_director.director.demo import build_tracking_demo
from ai_previz_director.director.export import export_clean_video


ARTIFACTS = ROOT / "tests" / "artifacts"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def evaluated_location(obj):
    return obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation.copy()


result = build_tracking_demo(str(ARTIFACTS / "tracking_demo.blend"))
scene = bpy.context.scene
expected = {
    1: "CAM_Actor_Follow",
    48: "CAM_Actor_Follow",
    49: "CAM_Car_Chase",
    96: "CAM_Car_Chase",
    97: "CAM_Wide_Cut",
    120: "CAM_Wide_Cut",
}
switches = {}
for frame, camera_name in expected.items():
    scene.frame_set(frame)
    switches[frame] = scene.camera.name
    if scene.camera.name != camera_name:
        raise AssertionError({"frame": frame, "expected": camera_name, "actual": scene.camera.name})

scene.frame_set(1)
actor_camera_start = evaluated_location(bpy.data.objects["CAM_Actor_Follow"])
scene.frame_set(48)
actor_camera_end = evaluated_location(bpy.data.objects["CAM_Actor_Follow"])
if actor_camera_end.x - actor_camera_start.x < 9.5:
    raise AssertionError({"actor_camera_start": list(actor_camera_start), "actor_camera_end": list(actor_camera_end)})

scene.frame_set(49)
car_camera_start = evaluated_location(bpy.data.objects["CAM_Car_Chase"])
scene.frame_set(96)
car_camera_end = evaluated_location(bpy.data.objects["CAM_Car_Chase"])
if car_camera_end.x - car_camera_start.x < 17.5:
    raise AssertionError({"car_camera_start": list(car_camera_start), "car_camera_end": list(car_camera_end)})

video = export_clean_video(str(ARTIFACTS / "tracking_demo.mp4"), 1, 120)
if not video["exists"] or os.path.getsize(video["path"]) <= 0:
    raise AssertionError(video)

summary = {
    "status": "PASS",
    "build": result,
    "camera_switches": switches,
    "actor_follow_delta_x": actor_camera_end.x - actor_camera_start.x,
    "car_follow_delta_x": car_camera_end.x - car_camera_start.x,
    "video": video,
    "video_bytes": os.path.getsize(video["path"]),
}
(ARTIFACTS / "tracking_demo_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("AI_PREVIZ_TRACKING_DEMO_PASS", json.dumps(summary, ensure_ascii=False))
