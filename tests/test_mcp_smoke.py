from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]


async def run():
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "companion_mcp" / "server.py")],
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            required = {"previz_get_state", "camera_set_lens", "previz_export_clean", "previz_undo"}
            if not required.issubset(names):
                raise AssertionError({"missing": sorted(required - names), "tools": sorted(names)})
            result = await session.call_tool("previz_get_state", {})
            if result.isError:
                raise AssertionError(result)
            print(json.dumps({"status": "PASS", "tool_count": len(names), "tools": sorted(names)}, ensure_ascii=False))


asyncio.run(run())
