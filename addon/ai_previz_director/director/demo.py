from __future__ import annotations

import math
import os

import bpy

from .camera import follow
from .fcurves import action_fcurves
from .semantic import tag_entity
from .shot import create_shot


def _material(name: str, color: tuple[float, float, float, float]):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    principled = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
    if principled:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Roughness"].default_value = 0.55
    return material


def _cube(name, location, scale, material, parent=None):
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.parent = parent
    obj.location = location
    obj.scale = scale
    obj.data.materials.append(material)
    return obj


def _sphere(name, location, radius, material, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=(0, 0, 0), radius=radius)
    obj = bpy.context.object
    obj.name = name
    obj.parent = parent
    obj.location = location
    obj.data.materials.append(material)
    return obj


def _linear_action(obj):
    ad = obj.animation_data
    if not ad or not ad.action:
        return
    for curve in action_fcurves(ad.action, getattr(ad, "action_slot", None)):
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"


def _camera(scene, name, lens, location, entity_id, aliases):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = location
    tag_entity(obj, "CAMERA", entity_id, aliases)
    return obj


def build_tracking_demo(output_path: str) -> dict:
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    scene = bpy.data.scenes.new("AI_Previz_Tracking_Demo")
    bpy.context.window.scene = scene
    scene.frame_start = 1
    scene.frame_end = 120
    scene.render.fps = 24
    scene.render.resolution_x = 640
    scene.render.resolution_y = 360
    scene.render.resolution_percentage = 100
    scene.render.engine = "BLENDER_EEVEE"
    scene.world = bpy.data.worlds.new("AI_Previz_World")
    scene.world.color = (0.04, 0.05, 0.07)

    gray = _material("MAT_Ground", (0.08, 0.1, 0.12, 1.0))
    actor_mat = _material("MAT_Actor", (0.12, 0.42, 0.95, 1.0))
    skin = _material("MAT_Head", (0.8, 0.48, 0.3, 1.0))
    car_mat = _material("MAT_Car", (0.9, 0.08, 0.04, 1.0))
    dark = _material("MAT_Wheels", (0.015, 0.015, 0.02, 1.0))

    ground = _cube("Ground", (0, 0, -0.15), (15, 8, 0.15), gray)
    tag_entity(ground, "BACKGROUND", "ground_stage", ["地面", "道路"])

    actor = bpy.data.objects.new("ACTOR_Walker", None)
    scene.collection.objects.link(actor)
    tag_entity(actor, "ACTOR", "actor_walker", ["人物", "行人", "walker"])
    _cube("Actor_Body", (0, 0, 1.15), (0.36, 0.24, 0.8), actor_mat, actor)
    _sphere("Actor_Head", (0, 0, 2.2), 0.35, skin, actor)
    actor_focus = bpy.data.objects.new("Actor_Focus", None)
    scene.collection.objects.link(actor_focus)
    actor_focus.parent = actor
    actor_focus.location = (0, 0, 1.35)
    actor["previz_focus_object"] = actor_focus.name
    actor.location = (-6, 0, 0)
    actor.keyframe_insert("location", frame=1)
    actor.location = (4, 0, 0)
    actor.keyframe_insert("location", frame=48)
    actor.keyframe_insert("location", frame=120)
    _linear_action(actor)

    car = bpy.data.objects.new("CAR_Red", None)
    scene.collection.objects.link(car)
    tag_entity(car, "PROP", "car_red", ["汽车", "红车", "car"])
    _cube("Car_Body", (0, 0, 0.75), (1.7, 0.85, 0.42), car_mat, car)
    _cube("Car_Cabin", (-0.1, 0, 1.35), (0.8, 0.72, 0.42), car_mat, car)
    car_focus = bpy.data.objects.new("Car_Focus", None)
    scene.collection.objects.link(car_focus)
    car_focus.parent = car
    car_focus.location = (0, 0, 0.85)
    car["previz_focus_object"] = car_focus.name
    for x in (-1.05, 1.05):
        for y in (-0.9, 0.9):
            bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.38, depth=0.22, location=(0, 0, 0), rotation=(math.pi / 2, 0, 0))
            wheel = bpy.context.object
            wheel.name = f"Wheel_{x}_{y}"
            wheel.parent = car
            wheel.location = (x, y, 0.42)
            wheel.data.materials.append(dark)
    car.location = (-9, 2.7, 0)
    car.keyframe_insert("location", frame=1)
    car.keyframe_insert("location", frame=49)
    car.location = (9, 2.7, 0)
    car.keyframe_insert("location", frame=96)
    car.keyframe_insert("location", frame=120)
    _linear_action(car)

    actor_camera = _camera(scene, "CAM_Actor_Follow", 50, (0, -6.5, 3.0), "camera_actor_follow", ["人物跟拍"])
    car_camera = _camera(scene, "CAM_Car_Chase", 40, (-7, -5.0, 2.6), "camera_car_chase", ["汽车追踪"])
    wide_camera = _camera(scene, "CAM_Wide_Cut", 32, (0, -15, 9), "camera_wide_cut", ["大全景"])
    follow("camera_actor_follow", "actor_walker", (0, -6.5, 3.0))
    follow("camera_car_chase", "car_red", (-7, -5.0, 2.6))
    track = wide_camera.constraints.new("TRACK_TO")
    track.name = "AI_PREVIZ_FOLLOW_TRACK"
    track.target = car_focus
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    scene.camera = actor_camera
    create_shot("S01_ACTOR_FOLLOW", 1, 48, actor_camera.name, "actor_walker", "FOLLOW")
    create_shot("S02_CAR_CHASE", 49, 96, car_camera.name, "car_red", "CHASE")
    create_shot("S03_WIDE_CUT", 97, 120, wide_camera.name, "car_red", "WIDE")

    sun_data = bpy.data.lights.new("Sun_Key", "SUN")
    sun_data.energy = 2.2
    sun = bpy.data.objects.new("Sun_Key", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(30), math.radians(-20), math.radians(-35))
    tag_entity(sun, "LIGHT", "light_sun", ["主光"])
    area_data = bpy.data.lights.new("Area_Fill", "AREA")
    area_data.energy = 800
    area_data.shape = "DISK"
    area_data.size = 8
    area = bpy.data.objects.new("Area_Fill", area_data)
    scene.collection.objects.link(area)
    area.location = (0, -2, 10)

    scene.frame_set(1)
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=output_path)
    return {
        "path": output_path,
        "scene": scene.name,
        "frame_range": [scene.frame_start, scene.frame_end],
        "actor": actor.name,
        "car": car.name,
        "cameras": [actor_camera.name, car_camera.name, wide_camera.name],
        "shots": ["S01_ACTOR_FOLLOW", "S02_CAR_CHASE", "S03_WIDE_CUT"],
    }
