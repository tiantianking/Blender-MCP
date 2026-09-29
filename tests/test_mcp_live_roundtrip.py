from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "artifacts" / "live_default_scene.png"


def payload(result):
    if result.isError:
        raise AssertionError(result)
    structured = getattr(result, "structuredContent", None)
    if structured:
        return structured
    return json.loads(result.content[0].text)


async def run():
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "companion_mcp" / "server.py")],
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            initial = payload(await session.call_tool("previz_get_state", {}))
            initial_lens = float(initial["state"]["cameras"][0]["lens_mm"])
            test_lens = min(initial_lens + 5.0, 600.0)
            changed = False
            try:
                payload(await session.call_tool("camera_set_lens", {"lens_mm": test_lens}))
                changed = True
                after = payload(await session.call_tool("previz_get_state", {}))
                actual = float(after["state"]["cameras"][0]["lens_mm"])
                if abs(actual - test_lens) > 1e-6:
                    raise AssertionError({"expected": test_lens, "actual": actual})
                capture = payload(await session.call_tool("previz_capture_view", {"output_path": str(OUTPUT)}))
                payload(await session.call_tool("previz_undo", {}))
                changed = False
                restored = payload(await session.call_tool("previz_get_state", {}))
                restored_lens = float(restored["state"]["cameras"][0]["lens_mm"])
                if abs(restored_lens - initial_lens) > 1e-6:
                    raise AssertionError({"initial": initial_lens, "restored": restored_lens})
                print(json.dumps({
                    "status": "PASS",
                    "initial_lens": initial_lens,
                    "temporary_lens": actual,
                    "restored_lens": restored_lens,
                    "capture": capture,
                }, ensure_ascii=False))
            finally:
                if changed:
                    await session.call_tool("previz_undo", {})


asyncio.run(run())
