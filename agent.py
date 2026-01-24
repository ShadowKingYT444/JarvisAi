import asyncio
import os
import sys
import platform
import json
import re
import traceback

# NEW SDK
from google import genai
from google.genai import types

import nest_asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

# Apply nest_asyncio
nest_asyncio.apply()

# --- Configuration ---
API_KEY = os.getenv("GOOGLE_API_KEY") 
if not API_KEY:
    # Fallback to the one in the original file if env var is missing
    API_KEY = "AIzaSyCZi6VSgl4TAKxjyKBT83v906UGOxgmxRQ"

if not API_KEY:
    print("Error: GOOGLE_API_KEY environment variable not set.")
    sys.exit(1)

# Initialize Gemini Client
client = genai.Client(api_key=API_KEY)
MODEL_NAME = "gemini-2.0-flash-exp"

# MCP Configuration
MCP_COMMAND = "npx"
if os.name == "nt":
    MCP_COMMAND = "npx.cmd"

MCP_ARGS = ["-y", "@playwright/mcp@latest"]

class BrowserAgent:
    def __init__(self):
        self.session = None
        self.exit_stack = None
        self.tools = []
        self.tool_map = {}
        self.history = [] 

    async def start(self):
        """Starts the MCP session and fetches tools."""
        env = os.environ.copy()
        
        # REMOVED: env["BROWSER"] = ... 
        # We rely on Playwright's default (bundled Chromium) behavior to avoid PATH issues.
        # The Playwright MCP server defaults to headed (visible) mode unless --headless is passed.

        server_params = StdioServerParameters(
            command=MCP_COMMAND, args=MCP_ARGS, env=env
        )

        self.exit_stack = AsyncExitStack()

        try:
            read, write = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self.session.initialize()

            # Fetch tools
            result = await self.session.list_tools()
            self.tools = result.tools
            self.tool_map = {t.name: t for t in self.tools}
            print(f"Connected to Playwright MCP. Loaded {len(self.tools)} tools.")

        except Exception as e:
            print(f"Failed to start MCP session: {e}")
            sys.exit(1)

    async def stop(self):
        """Closes the MCP session."""
        if self.exit_stack:
            await self.exit_stack.aclose()

    def get_system_instruction(self):
        """Defines the agent's persona and capabilties."""
        tools_desc = []
        for t in self.tools:
            schema = json.dumps(t.inputSchema, separators=(",", ":"))
            tools_desc.append(f"- {t.name}: {t.description}\n  Schema: {schema}")
        
        tools_str = "\n".join(tools_desc)

        return f"""You are an advanced AI Browser Agent.
You have full access to a real browser via Playwright tools.
Your goal is to accomplish the user's tasks by interacting with web pages just like a human user would.

**Capabilities**:
- Navigate to URLs (`browser_navigate`).
- Click elements (`browser_click`), fill forms (`browser_fill_form`), type (`browser_type`).
- Read pages (`browser_screenshot`, `browser_snapshot`).
- Execute JS (`browser_evaluate`).

**Available Tools**:
{tools_str}

**Instructions**:
1.  **Be Agentic**: Do not ask for permission for every step. If the user gives a high-level goal (e.g., "Open Google Docs and write a poem"), break it down and execute the steps autonomously.
2.  **Verify**: Use screenshots or snapshots to verify where you are and if your actions succeeded.
3.  **Error Handling**: If a step fails, analyze the error, maybe take a screenshot to understand the state, and try a different approach.
4.  **Output Format**: 
    To call tools, you MUST Output a JSON object (or a list of objects) inside a markdown code block.
    
    Example:
    ```json
    {{
      "tool": "browser_navigate",
      "args": {{ "url": "https://example.com" }}
    }}
    ```
    
    Or for multiple tools:
    ```json
    [
      {{ "tool": "browser_fill_form", "args": {{ ... }} }},
      {{ "tool": "browser_click", "args": {{ ... }} }}
    ]
    ```

    If you are done or need to talk to the user, just write normal text.
"""

    async def execute_tool(self, tool_name, arguments):
        """Executes a single tool via MCP."""
        if tool_name not in self.tool_map:
            return f"Error: Tool {tool_name} not found."

        try:
            print(f"DEBUG: Calling {tool_name} with {arguments}")
            result = await self.session.call_tool(tool_name, arguments)
            
            output = []
            if result.content:
                for item in result.content:
                    if hasattr(item, "text"):
                        output.append(item.text)
                    elif hasattr(item, "data"):
                        output.append(f"[Image Data: {len(item.data)} bytes]")
            return "\n".join(output)
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    async def run_loop(self, user_command):
        print(f"\n--- Processing: {user_command} ---")
        
        chat = client.aio.chats.create(
            model=MODEL_NAME,
            config=types.GenerateContentConfig(
                system_instruction=self.get_system_instruction(),
                temperature=0.0, 
            )
        )

        current_prompt = user_command
        MAX_TURNS = 20
        
        for i in range(MAX_TURNS):
            print(f"Turn {i+1}...")
            
            try:
                response = await chat.send_message(current_prompt)
                response_text = response.text
            except Exception as e:
                print(f"Error calling model: {e}")
                break

            # Parse tool calls
            tool_calls = []
            
            # Robust JSON extraction
            # 1. Try to find a JSON block inside ```json ... ```
            # 2. Try to find a JSON block inside ``` ... ```
            # 3. Try to find a bare JSON object/list if it looks like one
            
            json_matches = re.finditer(r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```", response_text, re.DOTALL)
            found_json = False
            
            for match in json_matches:
                try:
                    content = match.group(1)
                    parsed = json.loads(content)
                    if isinstance(parsed, list):
                        tool_calls.extend(parsed)
                    elif isinstance(parsed, dict):
                        tool_calls.append(parsed)
                    found_json = True
                except json.JSONDecodeError:
                    continue
            
            if not found_json:
                # Fallback: look for just a raw JSON start/end if almost the whole message is JSON
                try:
                    stripped = response_text.strip()
                    if (stripped.startswith("{") and stripped.endswith("}")) or \
                       (stripped.startswith("[") and stripped.endswith("]")):
                        parsed = json.loads(stripped)
                        if isinstance(parsed, list):
                            tool_calls.extend(parsed)
                        elif isinstance(parsed, dict):
                            tool_calls.append(parsed)
                        found_json = True
                except:
                    pass

            if not tool_calls:
                print(f"Agent: {response_text}")
                # If no tools, assume it's a response to user.
                # However, if it's the very first turn and the user asked for an action, the model might be hallucinating a text response.
                # But with the new prompt, it should be better.
                break

            # Execute tools
            tool_outputs = []
            for tc in tool_calls:
                t_name = tc.get("tool")
                # Sometimes models output 'tool_name' or 'function' instead of 'tool'
                if not t_name: t_name = tc.get("function")
                
                t_args = tc.get("args")
                if t_args is None: t_args = tc.get("arguments", {})
                if t_args is None: t_args = tc.get("tool_input", {}) # Previous agent format

                if not t_name:
                    tool_outputs.append("Error: parsed JSON but could not find 'tool' or 'function' name.")
                    continue

                print(f"   Executing Tool: {t_name}...")
                output = await self.execute_tool(t_name, t_args)
                tool_outputs.append(f"Tool '{t_name}' Output: {output}")
            
            current_prompt = "Tool Outputs:\n" + "\n".join(tool_outputs)

async def main():
    agent = BrowserAgent()
    await agent.start()

    print("\nAgent ready. Type 'exit' to quit.")

    while True:
        try:
            command = input("\nEnter command: ")
            if command.lower() in ["exit", "quit"]:
                break
            if not command.strip():
                continue

            await agent.run_loop(command)

        except KeyboardInterrupt:
            break
        except Exception as e:
            traceback.print_exc()

    await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
