
import asyncio
import os
import sys
import json
import re
import traceback
import subprocess
import webbrowser
from google import genai
from google.genai import types
import nest_asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack
import pyautogui
from PIL import Image
import PIL.ImageGrab
import io

# Apply nest_asyncio
nest_asyncio.apply()

# --- Configuration ---
API_KEY = os.getenv("GOOGLE_API_KEY") or "AIzaSyCZi6VSgl4TAKxjyKBT83v906UGOxgmxRQ"
MODEL_NAME = "gemini-2.0-flash-exp"

# MCP Configuration
MCP_COMMAND = "npx"
if os.name == "nt":
    MCP_COMMAND = "npx.cmd"
MCP_ARGS = ["-y", "@playwright/mcp@latest"]

class AgentService:
    def __init__(self):
        self.session = None
        self.exit_stack = None
        self.tools = []
        self.tool_map = {}
        self.chat = None
        self.client = None

    async def initialize(self):
        """Starts the MCP session and initializes Gemini."""
        if not API_KEY:
            print("Error: GOOGLE_API_KEY environment variable not set.")
            return

        self.client = genai.Client(api_key=API_KEY)
        
        # Start MCP (Playwright) - Just in case we need it, though we prioritize webbrowser
        env = os.environ.copy()
        server_params = StdioServerParameters(command=MCP_COMMAND, args=MCP_ARGS, env=env)
        self.exit_stack = AsyncExitStack()

        try:
            read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
            self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            
            # Fetch tools
            result = await self.session.list_tools()
            self.tools = result.tools
            self.tool_map = {t.name: t for t in self.tools}
            print(f"Connected to Playwright MCP. Loaded {len(self.tools)} tools.")
            
        except Exception as e:
            print(f"Failed to start MCP session: {e}")
            # Continue without MCP if it fails, as we have local tools
            self.tools = []

        # Local Tools Registry
        self.register_local_tools()

    def register_local_tools(self):
        # We manually add local tools to the prompt description
        pass

    async def cleanup(self):
        if self.exit_stack:
            await self.exit_stack.aclose()

    # Duplicate get_system_instruction removed.


    async def execute_tool(self, tool_name, args):
        print(f"Executing {tool_name} with {args}")
        
        # Local Tools
        if tool_name == "open_url":
            webbrowser.open(args.get("url"))
            return "Opened URL in default browser."
            
        if tool_name == "click_at":
            try:
                x_model = int(args.get("x", 0))
                y_model = int(args.get("y", 0))
                
                # Apply scaling
                # The model sees 'new_w' x 'new_h'.
                # The system is 'sys_w' x 'sys_h'.
                # scale = sys / new
                
                if hasattr(self, 'scale_x'):
                    x_real = int(x_model * self.scale_x)
                    y_real = int(y_model * self.scale_y)
                    print(f"DEBUG: Mapping {x_model},{y_model} (Model) -> {x_real},{y_real} (System)")
                else:
                    x_real, y_real = x_model, y_model

                pyautogui.click(x_real, y_real, duration=0.2)
                return f"Clicked at {x_real}, {y_real}"
            except Exception as e:
                return f"Error clicking: {e}"
            
        elif tool_name == "type_text":
            text = args.get("text", "")
            pyautogui.write(text, interval=0.01) # Small interval for reliability
            return f"Typed: {text}"
            
        elif tool_name == "press_key":
            key = args.get("key", "")
            pyautogui.press(key)
            return f"Pressed key: {key}"

        # MCP Tools
        if tool_name in self.tool_map:
            try:
                result = await self.session.call_tool(tool_name, args)
                output = []
                if result.content:
                    for item in result.content:
                        if hasattr(item, "text"):
                            output.append(item.text)
                return "\n".join(output)
            except Exception as e:
                return f"Error executing MCP tool {tool_name}: {e}"

        return f"Error: Tool {tool_name} not found."

    def _parse_tools(self, text):
        tool_calls = []
        # JSON Block Regex
        matches = re.finditer(r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```", text, re.DOTALL)
        for match in matches:
            try:
                content = match.group(1)
                parsed = json.loads(content)
                if isinstance(parsed, list): tool_calls.extend(parsed)
                elif isinstance(parsed, dict): tool_calls.append(parsed)
            except: pass
            
        if not tool_calls:
             # Try raw json
             try:
                 stripped = text.strip()
                 if (stripped.startswith("{") and stripped.endswith("}")) or \
                    (stripped.startswith("[") and stripped.endswith("]")):
                        parsed = json.loads(stripped)
                        if isinstance(parsed, list): tool_calls.extend(parsed)
                        elif isinstance(parsed, dict): tool_calls.append(parsed)
             except: pass
             
        return tool_calls

    def get_system_instruction(self):
        mcp_tools_desc = []
        for t in self.tools:
            mcp_tools_desc.append(f"- {t.name}: {t.description}")
            
        mcp_tools_str = "\n".join(mcp_tools_desc)

        return f"""You are an advanced AI OS Assistant.
You have access to the user's screen via screenshots and can interact with the computer.

**Goal**: Help the user by navigating the web or performing tasks on their screen.

**Critical Permissions & Capabilities**:
1. **VISUAL INTERACTION**: You HAVE permission to click and type anywhere. DO NOT ASK. Just do it.
2. **COORDINATES**: Use the coordinates *as you see them in the image*. The system scales them automatically.
3. **EXISTING BROWSER**: Use `open_url` to open tabs.
4. **ACT NOW**: Perform actions immediately.

**Execution Loop**:
You are running in a loop. After you execute an action (like opening a URL), you will receive a NEW screenshot of the result. 
- **CONTINUE** working step-by-step until the goal is achieved.
- **TERMINATE** when the task is fully complete.

**Available Tools**:
1. `open_url(url)`: Open URL in default browser.
2. `click_at(x, y)`: Move mouse to (x, y) and click.
3. `type_text(text)`: Type text.
4. `press_key(key)`: Press key (e.g. 'enter').
5. `terminate()`: Call this when the user's request is FULLY satisfied.
6. Playwright Tools (Fallback):
{mcp_tools_str}

**Input Format**:
Text command + Screenshot.

**Output Format**:
JSON list of tools.

Example (Multi-step):
User: "Go to github and click profile"
Turn 1:
```json
{{ "tool": "open_url", "args": {{ "url": "https://github.com" }} }}
```
(System acts, waits, sends new screenshot of Github)
Turn 2:
```json
{{ "tool": "click_at", "args": {{ "x": 900, "y": 80 }} }}
```
(System acts, waits, sends new screenshot)
Turn 3:
```json
{{ "tool": "terminate", "args": {{}} }}
```
"""

    async def process_request(self, text_command, screenshot_image=None):
        """
        Process a request with a feedback loop.
        """
        if not self.client:
            await self.initialize()

        # Create Chat Session
        # We need a chat session to maintain history across the loop turns
        self.chat = self.client.aio.chats.create(
            model=MODEL_NAME,
            config=types.GenerateContentConfig(
                system_instruction=self.get_system_instruction(),
                temperature=0.0
            )
        )

        current_prompt = text_command
        current_image = screenshot_image
        
        MAX_TURNS = 10
        history_log = []

        for turn in range(MAX_TURNS):
            print(f"--- Turn {turn + 1}/{MAX_TURNS} ---")
            
            # Prepare Content
            contents = [current_prompt]
            if current_image:
                # Resize
                max_size = (1024, 1024)
                # We need a copy because thumbnail executes in place
                img_copy = current_image.copy()
                img_copy.thumbnail(max_size)
                new_w, new_h = img_copy.size
                
                # Update Scaling
                sys_w, sys_h = pyautogui.size()
                self.scale_x = sys_w / new_w
                self.scale_y = sys_h / new_h
                print(f"DEBUG: Scale {self.scale_x:.2f}")
                
                contents.append(img_copy)
            else:
                self.scale_x = 1.0
                self.scale_y = 1.0

            try:
                response = await self.chat.send_message(contents)
                response_text = response.text
                print(f"Model: {response_text}")
                history_log.append(f"Turn {turn+1}: {response_text}")

                # Parse Tools
                tool_calls = self._parse_tools(response_text)
                
                if not tool_calls:
                    # No tools called, assuming done or question answered
                    return response_text

                executed_any = False
                output_msgs = []
                
                for tc in tool_calls:
                    t_name = tc.get("tool")
                    t_args = tc.get("args", {})
                    
                    if t_name == "terminate":
                        print("Agent terminated task.")
                        return "Task Completed."
                    
                    res = await self.execute_tool(t_name, t_args)
                    output_msgs.append(f"Tool {t_name}: {res}")
                    executed_any = True

                if not executed_any:
                    return response_text

                # Dynamic Wait
                wait_time = 1.0
                for tc in tool_calls:
                    if tc.get("tool") == "open_url":
                        wait_time = 3.0 # Longer wait for page load
                    elif tc.get("tool") in ["type_text", "click_at"]:
                         # If we just clicked/typed, maybe a shorter wait is ok, but safer to stick to 1s?
                         # Let's try 1.5s for click to be safe, 0.5s for type
                         if tc.get("tool") == "type_text": wait_time = max(wait_time, 0.5)
                         else: wait_time = max(wait_time, 1.5)

                print(f"DEBUG: Waiting {wait_time}s for UI update...")
                await asyncio.sleep(wait_time)

                # Capture NEW STATE
                current_image = PIL.ImageGrab.grab()
                current_prompt = "Task update: " + "; ".join(output_msgs) + ". See attached new screenshot. Continue or terminate."

            except Exception as e:
                traceback.print_exc()
                return f"Error in loop: {e}"

        return "Max turns reached."

# Singleton instance
agent_service = AgentService()
