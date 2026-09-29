from __future__ import annotations

import os
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))

from ai_previz_director.director.export import export_clean_video


def run():
    scene = bpy.context.scene
    scene.render.resolution_x = 320
    scene.render.resolution_y = 180
    scene.render.resolution_percentage = 100
    result = export_clean_video(str(ROOT / "tests" / "artifacts" / "clean_previz.mp4"), 1, 3)
    if not result["exists"] or os.path.getsize(result["path"]) <= 0:
        raise AssertionError(result)
    print("AI_PREVIZ_VIDEO_EXPORT_PASS", result, os.path.getsize(result["path"]))


run()
