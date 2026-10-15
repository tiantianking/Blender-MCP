import bpy


class AIPREVIZ_PG_Settings(bpy.types.PropertyGroup):
    prompt: bpy.props.StringProperty(name="Prompt", description="Natural-language previz instruction")
    mode: bpy.props.EnumProperty(name="Mode", items=[("quick", "Quick", "Low-latency fixed commands"), ("director", "Director Agent", "Autonomous Blender MCP agent")], default="quick")
    agent_backend: bpy.props.EnumProperty(
        name="Agent",
        items=[
            ("codex", "Codex", "Use Codex with Blender MCP"),
            ("gemini", "Gemini", "Use Gemini Pro through Antigravity with Blender MCP"),
        ],
        default="codex",
    )
    reference_image: bpy.props.StringProperty(
        name="Reference Image",
        description="Optional image supplied to the Director Agent",
        subtype="FILE_PATH",
    )
    workflow_stage: bpy.props.EnumProperty(
        name="Stage",
        items=[
            ("single", "单次任务", "完成整个任务并逐步核验"),
            ("layout", "白模布局", "只完成道路、占地、高度和空间关系"),
            ("detail", "资产细化", "保持布局并替换资产、丰富变化"),
            ("finish", "灯光运镜", "完善材质、灯光、摄像机和渲染"),
        ],
        default="single",
    )
    bridge_status: bpy.props.StringProperty(name="Bridge", default="Disconnected")
    ai_status: bpy.props.StringProperty(name="AI", default="Unknown")
    last_result: bpy.props.StringProperty(name="Last Result", default="No transaction yet")
    last_error: bpy.props.StringProperty(name="Error", default="")
    last_checkpoint: bpy.props.StringProperty(name="Checkpoint", default="", subtype="FILE_PATH")
    busy: bpy.props.BoolProperty(name="Busy", default=False)
