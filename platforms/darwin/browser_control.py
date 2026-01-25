"""
Browser Control via AppleScript (macOS)
Alternative to CDP when remote debugging is blocked by admin policy.

Works with Chrome and Safari without requiring special launch flags.
"""

import subprocess
import json
from typing import Optional

class MacOSBrowserControl:
    """
    Control Chrome or Safari tabs using AppleScript.
    No debug mode required - works on managed Macs.
    """
    
    def __init__(self, browser: str = "chrome"):
        """
        Args:
            browser: "chrome" or "safari"
        """
        self.browser = browser.lower()
        if self.browser == "chrome":
            self.app_name = "Google Chrome"
        elif self.browser == "safari":
            self.app_name = "Safari"
        else:
            raise ValueError(f"Unsupported browser: {browser}")
    
    def _run_applescript(self, script: str) -> tuple[bool, str]:
        """Run an AppleScript and return (success, output)."""
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "Script timed out"
        except Exception as e:
            return False, str(e)
    
    def get_tabs(self) -> list[dict]:
        """
        Get all open tabs from the browser.
        
        Returns:
            List of dicts with {id, title, url, window_id, tab_index}
        """
        if self.browser == "chrome":
            script = '''
            set output to ""
            tell application "Google Chrome"
                set windowCount to count of windows
                repeat with w from 1 to windowCount
                    set tabCount to count of tabs of window w
                    repeat with t from 1 to tabCount
                        set tabTitle to title of tab t of window w
                        set tabURL to URL of tab t of window w
                        set output to output & w & "|||" & t & "|||" & tabTitle & "|||" & tabURL & "\\n"
                    end repeat
                end repeat
            end tell
            return output
            '''
        else:  # Safari
            script = '''
            set output to ""
            tell application "Safari"
                set windowCount to count of windows
                repeat with w from 1 to windowCount
                    set tabCount to count of tabs of window w
                    repeat with t from 1 to tabCount
                        set tabTitle to name of tab t of window w
                        set tabURL to URL of tab t of window w
                        set output to output & w & "|||" & t & "|||" & tabTitle & "|||" & tabURL & "\\n"
                    end repeat
                end repeat
            end tell
            return output
            '''
        
        success, output = self._run_applescript(script)
        
        if not success:
            print(f"[BrowserControl] Error getting tabs: {output}")
            return []
        
        tabs = []
        tab_id = 0
        
        for line in output.strip().split("\n"):
            if not line or "|||" not in line:
                continue
            
            parts = line.split("|||")
            if len(parts) >= 4:
                tabs.append({
                    "id": tab_id,
                    "window_id": int(parts[0]),
                    "tab_index": int(parts[1]),
                    "title": parts[2],
                    "url": parts[3]
                })
                tab_id += 1
        
        return tabs
    
    def switch_to_tab(self, window_id: int, tab_index: int) -> bool:
        """
        Switch to a specific tab.
        
        Args:
            window_id: The window number (1-indexed)
            tab_index: The tab index within the window (1-indexed)
            
        Returns:
            True if successful
        """
        if self.browser == "chrome":
            script = f'''
            tell application "Google Chrome"
                set active tab index of window {window_id} to {tab_index}
                set index of window {window_id} to 1
                activate
            end tell
            '''
        else:
            script = f'''
            tell application "Safari"
                set current tab of window {window_id} to tab {tab_index} of window {window_id}
                set index of window {window_id} to 1
                activate
            end tell
            '''
        
        success, output = self._run_applescript(script)
        return success
    
    def switch_to_tab_by_id(self, tab_id: int) -> str:
        """
        Switch to a tab by its ID (from get_tabs()).
        
        Args:
            tab_id: The tab ID
            
        Returns:
            Result message
        """
        tabs = self.get_tabs()
        for tab in tabs:
            if tab["id"] == tab_id:
                success = self.switch_to_tab(tab["window_id"], tab["tab_index"])
                if success:
                    return f"Switched to: {tab['title']}"
                else:
                    return f"Failed to switch to tab {tab_id}"
        return f"Tab {tab_id} not found"
    
    def switch_to_tab_by_keyword(self, keyword: str) -> str:
        """
        Switch to the first tab matching a keyword in title or URL.
        
        Args:
            keyword: Search keyword
            
        Returns:
            Result message
        """
        keyword_lower = keyword.lower()
        tabs = self.get_tabs()
        
        for tab in tabs:
            if keyword_lower in tab["title"].lower() or keyword_lower in tab["url"].lower():
                success = self.switch_to_tab(tab["window_id"], tab["tab_index"])
                if success:
                    return f"Switched to: {tab['title']}"
                else:
                    return f"Failed to switch to matching tab"
        
        return f"No tab found matching '{keyword}'"
    
    def close_tab(self, window_id: int, tab_index: int) -> bool:
        """
        Close a specific tab.
        
        Args:
            window_id: The window number (1-indexed)
            tab_index: The tab index within the window (1-indexed)
            
        Returns:
            True if successful
        """
        if self.browser == "chrome":
            script = f'''
            tell application "Google Chrome"
                close tab {tab_index} of window {window_id}
            end tell
            '''
        else:
            script = f'''
            tell application "Safari"
                close tab {tab_index} of window {window_id}
            end tell
            '''
        
        success, _ = self._run_applescript(script)
        return success
    
    def close_tab_by_id(self, tab_id: int) -> str:
        """
        Close a tab by its ID.
        
        Args:
            tab_id: The tab ID from get_tabs()
            
        Returns:
            Result message
        """
        tabs = self.get_tabs()
        for tab in tabs:
            if tab["id"] == tab_id:
                title = tab["title"]
                success = self.close_tab(tab["window_id"], tab["tab_index"])
                if success:
                    return f"Closed: {title}"
                else:
                    return f"Failed to close tab {tab_id}"
        return f"Tab {tab_id} not found"
    
    def get_active_tab(self) -> Optional[dict]:
        """Get the currently active/frontmost tab using AppleScript."""
        if self.browser == "chrome":
            script = '''
            tell application "Google Chrome"
                set activeTab to active tab of front window
                set tabTitle to title of activeTab
                set tabURL to URL of activeTab
                return tabTitle & "|||" & tabURL
            end tell
            '''
        else:
            script = '''
            tell application "Safari"
                set activeTab to current tab of window 1
                set tabTitle to name of activeTab
                set tabURL to URL of activeTab
                return tabTitle & "|||" & tabURL
            end tell
            '''
            
        success, output = self._run_applescript(script)
        
        if success and "|||" in output:
            parts = output.strip().split("|||")
            if len(parts) >= 2:
                return {
                    "title": parts[0],
                    "url": parts[1]
                }
        return None

    def close_active_tab(self) -> bool:
        """Close the currently active tab."""
        if self.browser == "chrome":
            script = '''
            tell application "Google Chrome"
                close active tab of front window
            end tell
            '''
        else:
            script = '''
            tell application "Safari"
                close current tab of window 1
            end tell
            '''
        
        success, _ = self._run_applescript(script)
        return success

    def open_url(self, url: str, new_tab: bool = True) -> bool:
        """
        Open a URL in the browser.
        
        Args:
            url: The URL to open
            new_tab: If True, open in a new tab; otherwise use current tab
            
        Returns:
            True if successful
        """
        if self.browser == "chrome":
            if new_tab:
                script = f'''
                tell application "Google Chrome"
                    activate
                    tell window 1
                        make new tab with properties {{URL:"{url}"}}
                    end tell
                end tell
                '''
            else:
                script = f'''
                tell application "Google Chrome"
                    activate
                    set URL of active tab of window 1 to "{url}"
                end tell
                '''
        else:
            if new_tab:
                script = f'''
                tell application "Safari"
                    activate
                    tell window 1
                        set newTab to make new tab
                        set URL of newTab to "{url}"
                    end tell
                end tell
                '''
            else:
                script = f'''
                tell application "Safari"
                    activate
                    set URL of current tab of window 1 to "{url}"
                end tell
                '''
        
        success, _ = self._run_applescript(script)
        return success

    def scour_tabs(self, distraction_patterns: list[str]):
        """
        Cycle through tabs and close any that match the distraction patterns.
        On macOS, we can do this without visually switching tabs if we want,
        but for parity with Windows/consistency, we'll just iterate the list we get.
        """
        print(f"\\n🧹 STARTING TAB SWEEP (Checking for distractions)...")
        
        # 1. Get all tabs
        tabs = self.get_tabs()
        if not tabs:
            print("  No active tabs found.")
            return

        tabs_closed = 0
        
        # 2. Iterate and close distractions
        # We iterate backwards or carefully so we don't invalidate indices?
        # Ideally, we close by ID if supported, but our close_tab takes (window, index).
        # Closing a tab changes the indices of subsequent tabs in that window.
        # So it is SAFEST to sort by window, then by index DESCENDING.
        
        tabs.sort(key=lambda x: (x["window_id"], x["tab_index"]), reverse=True)
        
        for tab in tabs:
            title = tab["title"]
            url = tab["url"]
            
            # Check Distraction
            is_distraction = False
            for p in distraction_patterns:
                if p in url.lower() or p in title.lower():
                    is_distraction = True
                    break
            
            if is_distraction:
                print(f"  ❌ DISTRACTION DETECTED! Closing: {title[:20]}...")
                success = self.close_tab(tab["window_id"], tab["tab_index"])
                if success:
                    tabs_closed += 1
            # else:
            #     print(f"  ✅ Safe: {title[:20]}...")

        print(f"🧹 SWEEP COMPLETE. Closed {tabs_closed} tabs.\\n")
