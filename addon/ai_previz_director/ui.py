import json

import bpy

from .rpc_client import CLIENT, UI_RESULTS, send_prompt_async


def poll_ui_results() -> float:
    settings = getattr(bpy.context.scene, "ai_previz_settings", None)
    if not settings:
        return 0.25
    settings.bridge_status = "Connected" if CLIENT.connected else "Disconnected"
    try:
        result = UI_RESULTS.get_nowait()
    except Exception:
        return 0.25
    settings.busy = False
    if result.get("ok"):
        tx = result.get("transaction") or result.get("result", {}).get("transaction") or {}
        settings.last_result = f"Committed {tx.get('transaction_id', '')[:8]}" if tx else "Completed"
        settings.last_error = ""
    else:
        settings.last_error = result.get("error", "Unknown error")
        settings.last_result = "Failed"
    return 0.1


class AIPREVIZ_OT_Send(bpy.types.Operator):
    bl_idname = "ai_previz.send"
    bl_label = "Send"
    bl_description = "Compile and execute a structured previz intent"

    def execute(self, context):
        settings = context.scene.ai_previz_settings
        if not settings.prompt.strip():
            self.report({"WARNING"}, "Enter a prompt")
            return {"CANCELLED"}
        settings.busy = True
        settings.last_error = ""
        send_prompt_async(settings.prompt.strip(), settings.mode)
        return {"FINISHED"}


class AIPREVIZ_OT_Undo(bpy.types.Operator):
    bl_idname = "ai_previz.undo"
    bl_label = "Undo"

    def execute(self, context):
        context.scene.ai_previz_settings.busy = True
        send_prompt_async("撤销刚才修改", "quick")
        return {"FINISHED"}


class AIPREVIZ_OT_Redo(bpy.types.Operator):
    bl_idname = "ai_previz.redo"
    bl_label = "Redo"

    def execute(self, context):
        context.scene.ai_previz_settings.busy = True
        send_prompt_async("重做刚才修改", "quick")
        return {"FINISHED"}


class AIPREVIZ_PT_Main(bpy.types.Panel):
    bl_label = "AI Previz Director"
    bl_idname = "AIPREVIZ_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Previz"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ai_previz_settings
        scene = context.scene
        camera = scene.camera
        layout.label(text=f"Bridge: {settings.bridge_status}", icon="LINKED" if CLIENT.connected else "UNLINKED")
        layout.label(text=f"Camera: {camera.name if camera else 'None'}")
        layout.label(text=f"Lens: {camera.data.lens:.1f} mm" if camera else "Lens: —")
        layout.label(text=f"Frame: {scene.frame_current} / {scene.frame_end}")
        layout.prop(settings, "prompt", text="")
        layout.prop(settings, "mode", expand=True)
        row = layout.row()
        row.enabled = not settings.busy
        row.operator("ai_previz.send", icon="PLAY")
        row = layout.row(align=True)
        row.operator("ai_previz.undo", icon="LOOP_BACK")
        row.operator("ai_previz.redo", icon="LOOP_FORWARDS")
        layout.separator()
        layout.label(text=settings.last_result)
        if settings.last_error:
            box = layout.box()
            box.alert = True
            box.label(text=settings.last_error[:120], icon="ERROR")

