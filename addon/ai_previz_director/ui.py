import json
import os
import textwrap

import bpy

from .rpc_client import CLIENT, UI_RESULTS, send_prompt_async
from .director.transaction import MANAGER


REFERENCE_DEFAULT_PROMPTS = {
    "single": "根据参考图尽量还原完整场景，并完成必要的视觉核验",
    "layout": "根据参考图在新的专用集合中尽量还原道路、地块、建筑占地、高度和白模布局；不得清空场景或删除现有对象",
    "detail": "根据参考图细化当前场景的建筑、资产、材质和环境变化，同时保持已确认布局",
    "finish": "根据参考图完善当前场景的材质、灯光、摄像机、运镜和最终视觉效果",
}


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
        settings.last_result = result.get("message") or (f"Committed {tx.get('transaction_id', '')[:8]}" if tx else "Completed")
        settings.last_error = ""
        if result.get("checkpoint"):
            settings.last_checkpoint = result["checkpoint"]
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
        reference_image = bpy.path.abspath(settings.reference_image) if settings.reference_image else ""
        if reference_image and not os.path.isfile(reference_image):
            self.report({"WARNING"}, "Reference image does not exist")
            return {"CANCELLED"}
        prompt = settings.prompt.strip()
        if not prompt and reference_image:
            prompt = REFERENCE_DEFAULT_PROMPTS.get(settings.workflow_stage, REFERENCE_DEFAULT_PROMPTS["single"])
        if not prompt:
            self.report({"WARNING"}, "请输入任务，或先选择参考图")
            return {"CANCELLED"}
        settings.busy = True
        settings.last_error = ""
        stage_labels = {"single": "单次任务", "layout": "白模布局", "detail": "资产细化", "finish": "灯光运镜"}
        settings.last_result = f"处理中：{stage_labels.get(settings.workflow_stage, '单次任务')}"
        send_prompt_async(
            prompt,
            settings.mode,
            settings.agent_backend,
            reference_image,
            settings.workflow_stage,
        )
        return {"FINISHED"}


class AIPREVIZ_OT_RestoreCheckpoint(bpy.types.Operator):
    bl_idname = "ai_previz.restore_checkpoint"
    bl_label = "恢复最近检查点"
    bl_description = "Open the recovery copy created before the latest Director task"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        path = context.scene.ai_previz_settings.last_checkpoint
        if not path or not os.path.isfile(path):
            self.report({"ERROR"}, "Checkpoint file is unavailable")
            return {"CANCELLED"}
        bpy.ops.wm.open_mainfile(filepath=path)
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
        if settings.mode == "director":
            layout.prop(settings, "agent_backend", text="Agent")
            layout.prop(settings, "workflow_stage", text="阶段")
            layout.prop(settings, "reference_image", text="参考图")
        row = layout.row()
        row.enabled = not settings.busy
        row.operator("ai_previz.send", icon="PLAY")
        row = layout.row(align=True)
        undo = row.row(align=True)
        undo.enabled = bool(MANAGER.undo_stack) and not settings.busy
        undo.operator("ai_previz.undo", icon="LOOP_BACK")
        redo = row.row(align=True)
        redo.enabled = bool(MANAGER.redo_stack) and not settings.busy
        redo.operator("ai_previz.redo", icon="LOOP_FORWARDS")
        if settings.mode == "director":
            restore = layout.row()
            restore.enabled = bool(settings.last_checkpoint and os.path.isfile(settings.last_checkpoint)) and not settings.busy
            restore.operator("ai_previz.restore_checkpoint", icon="RECOVER_LAST")
        layout.separator()
        for line in textwrap.wrap(settings.last_result, width=34) or [""]:
            layout.label(text=line)
        if settings.last_error:
            box = layout.box()
            box.alert = True
            for index, line in enumerate(textwrap.wrap(settings.last_error, width=34) or [""]):
                box.label(text=line, icon="ERROR" if index == 0 else "NONE")
