from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))

import ai_previz_director
from ai_previz_director.dispatcher import DispatchRequest, _execute


with tempfile.TemporaryDirectory(prefix="ai-previz-checkpoint-") as temp:
    checkpoint = Path(temp) / "checkpoint.blend"
    original = bpy.data.filepath
    ai_previz_director.register()
    try:
        result = _execute(
            DispatchRequest(
                "checkpoint-smoke",
                "create_checkpoint",
                {"output_path": str(checkpoint)},
                lambda _result: None,
            )
        )
        assert result["ok"] is True, result
        assert checkpoint.is_file() and checkpoint.stat().st_size > 0
        assert bpy.data.filepath == original
        print("CHECKPOINT_SMOKE_OK", checkpoint.stat().st_size)
    finally:
        ai_previz_director.unregister()
