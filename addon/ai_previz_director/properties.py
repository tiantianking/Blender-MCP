import bpy


class AIPREVIZ_PG_Settings(bpy.types.PropertyGroup):
    prompt: bpy.props.StringProperty(name="Prompt", description="Natural-language previz instruction")
    mode: bpy.props.EnumProperty(name="Mode", items=[("quick", "Quick", "Low-latency single intent"), ("director", "Director", "Multi-operation director intent")], default="quick")
    bridge_status: bpy.props.StringProperty(name="Bridge", default="Disconnected")
    ai_status: bpy.props.StringProperty(name="AI", default="Unknown")
    last_result: bpy.props.StringProperty(name="Last Result", default="No transaction yet")
    last_error: bpy.props.StringProperty(name="Error", default="")
    busy: bpy.props.BoolProperty(name="Busy", default=False)

