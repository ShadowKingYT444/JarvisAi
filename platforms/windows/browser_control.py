"""
Windows Browser Control using UIAutomation and PyAutoGUI.
Supports Chrome, Edge, and Firefox by inspecting the active window.
"""

import subprocess
import time
import webbrowser
import pyautogui
from typing import Optional, List

# Try importing uiautomation
try:
    import uiautomation as auto
except ImportError:
    auto = None

class WindowsBrowserControl:
    """
    Control browsers on Windows (Chrome, Edge, Firefox).
    Uses UIAutomation to inspect the active tab and PyAutoGUI for actions.
    """
    
    def __init__(self, browser: str = "chrome"):
        # Browser arg is mostly ignored now as we detect the active window
        self.browser = browser.lower()

    def get_tabs(self) -> List[dict]:
        """
        Returns the ACTIVE tab as a list of 1.
        """
        active = self.get_active_tab()
        if active:
            return [{
                "id": 1, 
                "title": active["title"], 
                "url": active["url"], 
                "window_id": 1, 
                "tab_index": 1
            }]
        return []

    def get_active_tab(self) -> Optional[dict]:
        """
        Get the currently active tab from the FOCUSED window.
        Supports Chrome ("Chrome_WidgetWin_1"), Edge, and Firefox ("MozillaWindowClass").
        """
        if not auto:
            return None

        try:
            # 1. Get the currently focused window
            # This is key: We care about what the user is looking at RIGHT NOW.
            focused_element = auto.GetFocusedControl()
            if not focused_element:
                return None
                
            window = focused_element.GetTopLevelControl()
            if not window or not window.Exists(0, 0):
                return None

            class_name = window.ClassName
            full_title = window.Name
            
            # Identify Browser
            is_chrome_like = "Chrome_WidgetWin_1" in class_name
            is_firefox = "MozillaWindowClass" in class_name
            
            if not (is_chrome_like or is_firefox):
                # Not a browser (or at least not one we support yet)
                # We could return None, or maybe a generic "App" entry?
                # For Jarvis "Focus Mode", we really only care about Browsers for now.
                return None

            # 2. Extract Title
            title = full_title
            # Cleanup common suffixes
            for suffix in [" - Google Chrome", " - Microsoft Edge", " — Mozilla Firefox", " - Mozilla Firefox"]:
                title = title.replace(suffix, "")

            # 3. Extract URL
            url = ""
            
            if is_chrome_like:
                # Chrome/Edge Strategy: Look for "Address and search bar"
                # Sometimes retrieving the focused element directly gives us the OmniBox if user is typing
                
                # Check known names for Address Bar
                address_bar = window.EditControl(Name="Address and search bar", searchDepth=10)
                if not address_bar.Exists(0, 0):
                    address_bar = window.EditControl(Name="Address and search", searchDepth=10)
                
                if address_bar.Exists(0, 0):
                    try:
                        url = address_bar.GetValuePattern().Value
                    except: pass
                    
            elif is_firefox:
                # Firefox Strategy: 
                # Firefox UI structure is different. 
                # URL bar is often a ComboBox or Edit named "Search with Google or enter address" or similar.
                # It is often the first ComboBox in the Navigation Toolbar.
                
                # Strategy: Search broadly for the URL bar by common properties
                # Firefox 120+: "Navigation" tool bar -> "Search with Google or enter address" ComboBox
                
                nav_bar = window.ToolBarControl(Name="Navigation")
                if nav_bar.Exists(0, 0):
                    # Try finding the URL bar inside navigation
                    url_bar = nav_bar.ComboBoxControl(searchDepth=2) 
                    if not url_bar.Exists(0, 0):
                        url_bar = nav_bar.EditControl(searchDepth=2)
                    
                    if url_bar.Exists(0, 0):
                        try:
                            # Firefox often hides the "http" part in the Value Pattern until focused
                            # But let's try.
                            url = url_bar.GetValuePattern().Value
                        except: pass

            # 4. Cleanup & Validation
            if url:
                # Basic correction
                if not url.startswith("http") and not url.startswith("file://") and "." in url:
                    url = "https://" + url
                
                return {"title": title, "url": url}
            
            # Fallback: We have a title but no URL. 
            # Useful for "YouTube" title blocking even if we can't read the exact video URL.
            if title:
                return {"title": title, "url": "unknown://app"}
                
            return None

        except Exception as e:
            # print(f"Browser inspect error: {e}")
            return None

    def switch_to_tab(self, window_id: int, tab_index: int) -> bool:
        return False
        
    def switch_to_tab_by_keyword(self, keyword: str) -> str:
        # Generic Ctrl+Tab cycling
        print(f"Attempting to switch to {keyword}...")
        for _ in range(10):
            active = self.get_active_tab()
            if active and (keyword.lower() in active["title"].lower() or keyword.lower() in active["url"].lower()):
                return f"Found {active['title']}"
            
            pyautogui.hotkey('ctrl', 'tab')
            time.sleep(0.1)
            
        return "Tab not found"

    def close_tab(self, window_id: int, tab_index: int) -> bool:
        return self.close_active_tab()

    def close_active_tab(self) -> bool:
        # Standard shortcut for almost all browsers
        pyautogui.hotkey('ctrl', 'w')
        return True

    def open_url(self, url: str, new_tab: bool = True) -> bool:
        # Use Python's native webbrowser module.
        try:
            if new_tab:
                webbrowser.open_new_tab(url)
            else:
                webbrowser.open(url)
            return True
        except Exception as e:
            print(f"Failed to open URL: {e}")
            return False

    def scour_tabs(self, distraction_patterns: List[str]):
        """
        Cycle through tabs and close any that match the distraction patterns.
        """
        print(f"\n🧹 STARTING TAB SWEEP (Checking for distractions)...")
        checked_tabs = set()
        
        # Limit to 20 tabs to prevent infinite loops
        for i in range(20):
            # 1. Inspect current
            active = self.get_active_tab()
            if not active:
                print(f"  [Sweep {i+1}] No active tab found.")
                break
                
            title = active["title"]
            url = active["url"]
            print(f"  [Sweep {i+1}] Checking: {title[:20]}... ({url[:30]}...)")
            
            # Check overlap to avoid infinite loop (if we cycled back)
            # Use title+url as unique key
            tab_sig = f"{title}|||{url}"
            if tab_sig in checked_tabs:
                print("  -> Cycled back to start. Sweep complete.")
                break
            checked_tabs.add(tab_sig)
            
            # 2. Check Distraction
            is_distraction = False
            for p in distraction_patterns:
                if p in url.lower() or p in title.lower():
                    is_distraction = True
                    break
            
            if is_distraction:
                print(f"  ❌ DISTRACTION DETECTED! Closing.")
                self.close_active_tab()
                time.sleep(0.2) # Wait for close animation (optimized)
                # Note: valid tabs stay, distractions go.
                # After closing, the next tab becomes active automatically, so we don't need Ctrl+Tab
            else:
                print(f"  ✅ Safe. Next tab...")
                pyautogui.hotkey('ctrl', 'tab')
                time.sleep(0.1) # Wait for tab switch (optimized)
        
        print("🧹 SWEEP COMPLETE 🧹\n")
