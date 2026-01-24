"""
Smart Tab Manager for Jarvis Agent
Connects to existing Chrome browser via CDP and manages tabs.

SETUP INSTRUCTIONS:
===================
1. Close all Chrome instances completely

2. Launch Chrome with remote debugging enabled:

   macOS/Linux:
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

   Windows:
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

   Or create an alias in your shell:
   alias chrome-debug='/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222'

3. Open your tabs as usual in this Chrome window

4. Run Jarvis - it will now be able to see and switch between your tabs!
"""

import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class TabManager:
    """
    Manages browser tabs by connecting to an existing Chrome instance via CDP.
    """
    
    CDP_ENDPOINT = "http://localhost:9222"
    
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._connected = False
    
    async def connect(self) -> bool:
        """
        Connect to existing Chrome browser via CDP.
        Returns True if connected successfully, False otherwise.
        """
        if self._connected:
            return True
            
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.connect_over_cdp(self.CDP_ENDPOINT)
            
            # Get the default context (existing browser window)
            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
            else:
                # Create a new context if none exists
                self.context = await self.browser.new_context()
            
            self._connected = True
            print(f"[TabManager] Connected to Chrome via CDP. Found {len(self.context.pages)} tabs.")
            return True
            
        except Exception as e:
            print(f"[TabManager] Failed to connect to Chrome: {e}")
            print("[TabManager] Make sure Chrome is running with: --remote-debugging-port=9222")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from the browser."""
        if self.playwright:
            await self.playwright.stop()
        self._connected = False
        print("[TabManager] Disconnected.")
    
    async def scan_tabs(self) -> list[dict]:
        """
        Scan all open tabs and return their info.
        
        Returns:
            List of dicts with {id, title, url} for each tab.
        """
        if not self._connected:
            connected = await self.connect()
            if not connected:
                return []
        
        tabs = []
        try:
            pages = self.context.pages
            for idx, page in enumerate(pages):
                tabs.append({
                    "id": idx,
                    "title": await page.title() or "(No title)",
                    "url": page.url
                })
            return tabs
        except Exception as e:
            print(f"[TabManager] Error scanning tabs: {e}")
            return []
    
    async def switch_to_tab(self, identifier: str | int) -> str:
        """
        Switch to a tab by ID (index) or by keyword match in title/URL.
        
        Args:
            identifier: Tab index (int) or search keyword (str)
            
        Returns:
            Success/failure message string
        """
        if not self._connected:
            connected = await self.connect()
            if not connected:
                return "Error: Not connected to Chrome. Launch Chrome with --remote-debugging-port=9222"
        
        try:
            pages = self.context.pages
            target_page: Optional[Page] = None
            
            # If identifier is an integer, use it as index
            if isinstance(identifier, int):
                if 0 <= identifier < len(pages):
                    target_page = pages[identifier]
                else:
                    return f"Tab not found: index {identifier} out of range (0-{len(pages)-1})"
            
            # If identifier is a string, search by keyword
            elif isinstance(identifier, str):
                identifier_lower = identifier.lower()
                
                # Try to parse as integer first
                try:
                    idx = int(identifier)
                    if 0 <= idx < len(pages):
                        target_page = pages[idx]
                except ValueError:
                    pass
                
                # Search by title or URL
                if not target_page:
                    for page in pages:
                        title = (await page.title() or "").lower()
                        url = page.url.lower()
                        
                        if identifier_lower in title or identifier_lower in url:
                            target_page = page
                            break
            
            if target_page:
                await target_page.bring_to_front()
                title = await target_page.title()
                return f"Switched to tab: {title}"
            else:
                return f"Tab not found: No tab matching '{identifier}'"
                
        except Exception as e:
            return f"Error switching tabs: {e}"
    
    async def get_active_tab(self) -> Optional[dict]:
        """Get info about the currently active tab."""
        if not self._connected:
            return None
            
        try:
            # The last focused page is typically at the end or we need to check
            pages = self.context.pages
            if pages:
                # Return the first page as a fallback (Playwright doesn't track "active" directly)
                page = pages[0]
                return {
                    "id": 0,
                    "title": await page.title(),
                    "url": page.url
                }
        except:
            pass
        return None
    
    async def close_tab(self, identifier: str | int) -> str:
        """
        Close a tab by ID or keyword.
        
        Args:
            identifier: Tab index (int) or search keyword (str)
            
        Returns:
            Success/failure message
        """
        if not self._connected:
            connected = await self.connect()
            if not connected:
                return "Error: Not connected to Chrome."
        
        try:
            pages = self.context.pages
            target_page: Optional[Page] = None
            
            if isinstance(identifier, int):
                if 0 <= identifier < len(pages):
                    target_page = pages[identifier]
            elif isinstance(identifier, str):
                identifier_lower = identifier.lower()
                for page in pages:
                    title = (await page.title() or "").lower()
                    url = page.url.lower()
                    if identifier_lower in title or identifier_lower in url:
                        target_page = page
                        break
            
            if target_page:
                title = await target_page.title()
                await target_page.close()
                return f"Closed tab: {title}"
            else:
                return f"Tab not found: '{identifier}'"
                
        except Exception as e:
            return f"Error closing tab: {e}"
    
    async def new_tab(self, url: str = "about:blank") -> str:
        """
        Open a new tab with the given URL.
        
        Args:
            url: URL to open in the new tab
            
        Returns:
            Success/failure message
        """
        if not self._connected:
            connected = await self.connect()
            if not connected:
                return "Error: Not connected to Chrome."
        
        try:
            page = await self.context.new_page()
            await page.goto(url)
            await page.bring_to_front()
            return f"Opened new tab: {url}"
        except Exception as e:
            return f"Error opening new tab: {e}"


# Singleton instance for easy import
tab_manager = TabManager()


# --- Test/Demo ---
async def demo():
    """Demo function to test the TabManager."""
    tm = TabManager()
    
    connected = await tm.connect()
    if not connected:
        print("Could not connect. Make sure Chrome is running with --remote-debugging-port=9222")
        return
    
    print("\n--- Scanning Tabs ---")
    tabs = await tm.scan_tabs()
    for tab in tabs:
        print(f"  [{tab['id']}] {tab['title'][:50]} - {tab['url'][:50]}")
    
    if tabs:
        print("\n--- Switching to first tab ---")
        result = await tm.switch_to_tab(0)
        print(f"  {result}")
    
    await tm.disconnect()


if __name__ == "__main__":
    asyncio.run(demo())

