
import asyncio
import os
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

# Determine command
MCP_COMMAND = "npx"
if os.name == "nt":
    MCP_COMMAND = "npx.cmd"
MCP_ARGS = ["-y", "@playwright/mcp@latest"]

async def main():
    server_params = StdioServerParameters(
        command=MCP_COMMAND, args=MCP_ARGS, env=os.environ.copy()
    )
    
    async with AsyncExitStack() as stack:
        print("Starting MCP server...")
        read, write = await stack.enter_async_context(stdio_client(server_params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        
        print("Listing tools...")
        result = await session.list_tools()
        
        for tool in result.tools:
            print(f"--- Tool: {tool.name} ---")
            print(f"Description: {tool.description}")
            print(f"Schema: {json.dumps(tool.inputSchema, indent=2)}")
            print("\n")
            
if __name__ == "__main__":
    asyncio.run(main())
