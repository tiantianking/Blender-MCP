from __future__ import annotations

import os
import math
import shutil
import subprocess
import tempfile

import bpy

from .errors import ValidationError


def _ensure_camera():
    if not bpy.context.scene.camera:
        raise ValidationError("Scene has no active camera")


def _prepare_preview(scene):
    old_engine = scene.render.engine
    old_world = tuple(scene.world.color) if scene.world else None
    temp_light_obj = None
    scene.render.engine = "BLENDER_EEVEE"
    if scene.world:
        scene.world.color = (0.08, 0.08, 0.08)
    enabled_lights = [obj for obj in scene.objects if obj.type == "LIGHT" and not obj.hide_render]
    if not enabled_lights:
        light_data = bpy.data.lights.new("AI_PREVIZ_TEMP_SUN", type="SUN")
        light_data.energy = 2.0
        temp_light_obj = bpy.data.objects.new("AI_PREVIZ_TEMP_SUN", light_data)
        scene.collection.objects.link(temp_light_obj)
        temp_light_obj.rotation_euler = (math.radians(35), math.radians(-20), math.radians(-35))
    return old_engine, old_world, temp_light_obj


def _restore_preview(scene, preview_state):
    old_engine, old_world, temp_light_obj = preview_state
    if temp_light_obj:
        light_data = temp_light_obj.data
        bpy.data.objects.remove(temp_light_obj, do_unlink=True)
        bpy.data.lights.remove(light_data)
    scene.render.engine = old_engine
    if scene.world and old_world is not None:
        scene.world.color = old_world


def capture_clean_still(output_path: str) -> dict:
    _ensure_camera()
    scene = bpy.context.scene
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    old_path = scene.render.filepath
    old_format = scene.render.image_settings.file_format
    old_color_mode = scene.render.image_settings.color_mode
    preview_state = _prepare_preview(scene)
    try:
        scene.render.filepath = output_path
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        bpy.ops.render.render(write_still=True)
    finally:
        scene.render.filepath = old_path
        scene.render.image_settings.file_format = old_format
        scene.render.image_settings.color_mode = old_color_mode
        _restore_preview(scene, preview_state)
    return {"path": output_path, "exists": os.path.exists(output_path), "kind": "clean_still"}


def export_clean_video(output_path: str, frame_start: int | None = None, frame_end: int | None = None) -> dict:
    _ensure_camera()
    scene = bpy.context.scene
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    old = {
        "filepath": scene.render.filepath, "file_format": scene.render.image_settings.file_format,
        "color_mode": scene.render.image_settings.color_mode,
        "start": scene.frame_start, "end": scene.frame_end,
        "container": scene.render.ffmpeg.format, "codec": scene.render.ffmpeg.codec,
    }
    preview_state = _prepare_preview(scene)
    try:
        if frame_start is not None:
            scene.frame_start = int(frame_start)
        if frame_end is not None:
            scene.frame_end = int(frame_end)
        scene.render.image_settings.color_mode = "RGB"
        try:
            scene.render.filepath = os.path.splitext(output_path)[0]
            scene.render.image_settings.file_format = "FFMPEG"
            scene.render.ffmpeg.format = "MPEG4"
            scene.render.ffmpeg.codec = "H264"
            scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
            bpy.ops.render.render(animation=True)
            actual = scene.render.filepath + ".mp4"
        except (TypeError, ValueError):
            # Some Blender 5.2 Windows builds expose FFMPEG in RNA but disable it
            # dynamically. Render a lossless PNG sequence and use a local ffmpeg.
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise ValidationError("This Blender build has no movie output and ffmpeg was not found on PATH")
            with tempfile.TemporaryDirectory(prefix="ai-previz-") as temp_dir:
                scene.render.filepath = os.path.join(temp_dir, "frame_")
                scene.render.image_settings.file_format = "PNG"
                bpy.ops.render.render(animation=True)
                fps = scene.render.fps / scene.render.fps_base
                subprocess.run(
                    [
                        ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps),
                        "-start_number", str(scene.frame_start), "-i", os.path.join(temp_dir, "frame_%04d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", output_path,
                    ],
                    check=True,
                )
                actual = output_path
    finally:
        scene.render.filepath = old["filepath"]
        scene.render.image_settings.file_format = old["file_format"]
        scene.render.image_settings.color_mode = old["color_mode"]
        scene.frame_start, scene.frame_end = old["start"], old["end"]
        scene.render.ffmpeg.format, scene.render.ffmpeg.codec = old["container"], old["codec"]
        _restore_preview(scene, preview_state)
    return {"path": actual, "exists": os.path.exists(actual), "kind": "clean_video"}
