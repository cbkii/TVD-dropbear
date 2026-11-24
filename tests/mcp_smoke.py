# SPDX-License-Identifier: Apache-2.0
"""Real SDK stdio handshake and policy test; does not contact Android."""
import asyncio
import json
import pathlib
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test():
    script=pathlib.Path(__file__).resolve().parents[1]/"tools/tvd_mcp.py"
    with tempfile.TemporaryDirectory() as tmp:
        params=StdioServerParameters(command=sys.executable,args=[str(script),"--serial","fake","--expect-serial","fake","--workspace",tmp])
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tools=await session.list_tools()
                names={t.name for t in tools.tools}
                assert {"device_catalog","device_inspect","device_profile","device_test","device_snapshot","device_compare","device_evidence","device_capability_record"}<=names
                assert "device_exec" not in names
                catalog=await session.call_tool("device_catalog",{})
                assert not catalog.isError
                denied=await session.call_tool("device_keypress",{"key":"DOWN"})
                assert denied.isError
                denied=await session.call_tool("device_reference_mirror",{"paths":["/vendor/lib/a.so"]})
                assert denied.isError
                denied=await session.call_tool("device_ui_hierarchy",{})
                assert denied.isError
asyncio.run(test())
