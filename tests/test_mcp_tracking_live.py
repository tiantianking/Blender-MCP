from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]


def payload(result):
    if result.isError:
        raise AssertionError(result)
    structured = getattr(result, "structuredContent", None)
    return structured or json.loads(result.content[0].text)


async def run():
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "companion_mcp" / "server.py")], cwd=str(ROOT))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            required = {"camera_follow", "shot_create", "shot_set_camera", "previz_set_frame", "previz_build_tracking_demo"}
            if not required.issubset(names):
                raise AssertionError({"missing": sorted(required - names)})

            expected = {1: "CAM_Actor_Follow", 49: "CAM_Car_Chase", 97: "CAM_Wide_Cut"}
            switches = {}
            for frame, camera in expected.items():
                result = payload(await session.call_tool("previz_set_frame", {"frame": frame}))
                switches[frame] = result["state"]["scene"]["active_camera"]
                if switches[frame] != camera:
                    raise AssertionError({"frame": frame, "expected": camera, "actual": switches[frame]})

            payload(await session.call_tool("camera_follow", {
                "subject": "actor_walker", "camera": "camera_actor_follow",
                "offset_x": 0.0, "offset_y": -8.0, "offset_z": 3.2,
            }))
            moved = payload(await session.call_tool("previz_set_frame", {"frame": 24}))
            actor_camera = next(item for item in moved["state"]["cameras"] if item["id"] == "camera_actor_follow")
            if abs(float(actor_camera["location"][1]) + 8.0) > 1e-6:
                raise AssertionError(actor_camera)
            payload(await session.call_tool("previz_undo", {}))

            payload(await session.call_tool("shot_set_camera", {"shot": "S03_WIDE_CUT", "camera": "camera_car_chase"}))
            changed = payload(await session.call_tool("previz_set_frame", {"frame": 97}))
            if changed["state"]["scene"]["active_camera"] != "CAM_Car_Chase":
                raise AssertionError(changed)
            payload(await session.call_tool("previz_undo", {}))
            restored = payload(await session.call_tool("previz_set_frame", {"frame": 97}))
            if restored["state"]["scene"]["active_camera"] != "CAM_Wide_Cut":
                raise AssertionError(restored)

            print(json.dumps({
                "status": "PASS", "tool_count": len(names), "camera_switches": switches,
                "follow_offset_test": "PASS", "switch_and_undo_test": "PASS",
            }, ensure_ascii=False))


asyncio.run(run())
