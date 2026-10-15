bl_info = {
    "name": "AI Previz Director",
    "author": "OpenAI Codex",
    "version": (0, 4, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > AI Previz",
    "description": "Deterministic natural-language previz director companion",
    "category": "3D View",
}

import bpy

from .dispatcher import poll as poll_dispatcher
from .properties import AIPREVIZ_PG_Settings
from .rpc_client import CLIENT
from .ui import AIPREVIZ_OT_Send, AIPREVIZ_OT_Undo, AIPREVIZ_OT_Redo, AIPREVIZ_OT_RestoreCheckpoint, AIPREVIZ_PT_Main, poll_ui_results

CLASSES = (AIPREVIZ_PG_Settings, AIPREVIZ_OT_Send, AIPREVIZ_OT_Undo, AIPREVIZ_OT_Redo, AIPREVIZ_OT_RestoreCheckpoint, AIPREVIZ_PT_Main)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ai_previz_settings = bpy.props.PointerProperty(type=AIPREVIZ_PG_Settings)
    if not bpy.app.timers.is_registered(poll_dispatcher):
        bpy.app.timers.register(poll_dispatcher, first_interval=0.1, persistent=True)
    if not bpy.app.timers.is_registered(poll_ui_results):
        bpy.app.timers.register(poll_ui_results, first_interval=0.25, persistent=True)
    CLIENT.start()


def unregister():
    CLIENT.stop()
    if bpy.app.timers.is_registered(poll_dispatcher):
        bpy.app.timers.unregister(poll_dispatcher)
    if bpy.app.timers.is_registered(poll_ui_results):
        bpy.app.timers.unregister(poll_ui_results)
    if hasattr(bpy.types.Scene, "ai_previz_settings"):
        del bpy.types.Scene.ai_previz_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
