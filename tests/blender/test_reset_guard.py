from __future__ import annotations

import os
import sys
from pathlib import Path


ADDON_DIR = Path(os.environ["APPDATA"]) / "Blender Foundation/Blender/5.2/scripts/addons"
sys.path.insert(0, str(ADDON_DIR))

import blender_mcp


server = blender_mcp.BlenderMCPServer()
safe = server.execute_code("print('ok')")
assert safe["executed"] is True and safe["result"].strip() == "ok", safe

blocked = False
try:
    server.execute_code("bpy.ops.wm.read_factory_settings(use_empty=True)")
except Exception as exc:
    blocked = "Blocked unsafe Blender reset operation" in str(exc)

assert blocked, "read_factory_settings was not blocked"
print("RESET_GUARD_SMOKE_OK")
