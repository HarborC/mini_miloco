# test_mcp_http.py
import asyncio
from fastmcp.client import Client

async def main():
    client = Client("http://127.0.0.1:2324/mcp")

    async with client:
        tools = await client.list_tools()
        print("TOOLS:", [t.name for t in tools])

        devices = await client.call_tool("get_devices", {})
        print("DEVICES:", devices)

if __name__ == "__main__":
    asyncio.run(main())