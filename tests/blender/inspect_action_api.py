import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.object
obj.location.x = 0
obj.keyframe_insert("location", frame=1)
obj.location.x = 1
obj.keyframe_insert("location", frame=10)
action = obj.animation_data.action
print("ACTION_DIR", [x for x in dir(action) if not x.startswith("_")])
print("SLOT", obj.animation_data.action_slot, getattr(obj.animation_data.action_slot, "identifier", None))
for layer in action.layers:
    print("LAYER", layer.name, [x for x in dir(layer) if not x.startswith("_")])
    for strip in layer.strips:
        print("STRIP", strip.type, [x for x in dir(strip) if not x.startswith("_")])
        print("CHANNELBAGS", list(getattr(strip, "channelbags", [])))
        for bag in getattr(strip, "channelbags", []):
            print("BAG", bag.slot.handle, len(bag.fcurves), [(fc.data_path, fc.array_index, len(fc.keyframe_points)) for fc in bag.fcurves])
