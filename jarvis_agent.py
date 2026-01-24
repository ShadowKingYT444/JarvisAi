"""
Jarvis Agent - Fully Voice-Controlled Focus Assistant
No buttons needed - pure voice control with 24/7 distraction monitoring.

Features:
- Wake word activation ("Jarvis")
- Natural language command processing via Gemini
- Smart tab management (close, switch, open, restore)
- 24/7 distraction monitoring with 3-second warnings
- Audio feedback via system speech
"""

import os
import sys
import json
import re
import time
import threading
import subprocess
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Local imports
from wakeword.listener import WakeWordListener
from wakeword.stt import SpeechToText
from browser_control import AppleScriptBrowserControl
from focus_manager import FocusManager


class JarvisAgent:
    """
    Fully voice-controlled focus assistant with 24/7 monitoring.
    """
    
    BACKUP_FILE = "session_backup.json"
    MONITOR_INTERVAL = 2  # Check tabs every 2 seconds for faster response
    WARNING_COUNTDOWN = 3  # Seconds before auto-closing distraction
    
    # Distraction patterns (URLs/titles that are always distracting)
    DISTRACTION_PATTERNS = [
        "youtube.com", "netflix.com", "twitch.tv", "tiktok.com",
        "instagram.com", "facebook.com", "twitter.com", "x.com",
        "reddit.com", "9gag.com", "imgur.com",
        "discord.com", "slack.com",
        "valorant", "steam", "epic games", "playvalorant",
        "amazon.com", "ebay.com", "aliexpress", "shopping",
        "hulu.com", "disneyplus.com", "primevideo",
    ]
    
    # Productivity patterns (always allowed)
    PRODUCTIVITY_PATTERNS = [
        "github.com", "gitlab.com", "bitbucket.org",
        "stackoverflow.com", "docs.google.com", "notion.so",
        "figma.com", "linear.app", "jira", "confluence",
        "localhost", "127.0.0.1",
        "python.org", "developer.mozilla.org", "react.dev",
        "vscode", "cursor", "ide",
        "mail.google.com", "gmail.com", "outlook",
        "calendar.google.com", "drive.google.com",
    ]
    
    # Common site name to URL mapping
    SITE_URLS = {
        "gmail": "https://mail.google.com",
        "email": "https://mail.google.com",
        "google docs": "https://docs.google.com",
        "docs": "https://docs.google.com",
        "google drive": "https://drive.google.com",
        "drive": "https://drive.google.com",
        "github": "https://github.com",
        "youtube": "https://youtube.com",
        "google": "https://google.com",
        "calendar": "https://calendar.google.com",
        "notion": "https://notion.so",
        "figma": "https://figma.com",
        "twitter": "https://twitter.com",
        "x": "https://x.com",
        "instagram": "https://instagram.com",
        "facebook": "https://facebook.com",
        "reddit": "https://reddit.com",
        "linkedin": "https://linkedin.com",
        "stackoverflow": "https://stackoverflow.com",
        "stack overflow": "https://stackoverflow.com",
        "chatgpt": "https://chat.openai.com",
        "claude": "https://claude.ai",
        "amazon": "https://amazon.com",
        "netflix": "https://netflix.com",
        "spotify": "https://open.spotify.com",
    }
    
    def __init__(self):
        # Voice components
        self.listener = None
        self.stt = None
        
        # Browser control
        self.browser = AppleScriptBrowserControl("chrome")
        self.focus_manager = FocusManager()
        
        # Gemini client for intent parsing
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Missing GOOGLE_API_KEY in .env")
        self.gemini = genai.Client(api_key=api_key)
        self.model = "gemini-2.5-flash"  # Latest flash model
        
        # State
        self.current_goal = "General productivity"
        self.focus_mode_active = False  # When True, actively closes distractions
        self.monitoring_enabled = True
        self.running = True
        self.warned_tabs = {}  # tab_url -> warning_time
        self.last_active_url = None  # Track the last seen active tab
        
        # Threads
        self.monitor_thread = None
        self.voice_thread = None
        
        # Speech queue for sequential speech
        self.speech_queue = []
        self.speech_lock = threading.Lock()
        self.speech_thread = None
        self.speech_running = True
    
    def _speech_worker(self):
        """Background thread that processes speech queue one at a time."""
        while self.speech_running:
            text_to_speak = None
            
            with self.speech_lock:
                if self.speech_queue:
                    text_to_speak = self.speech_queue.pop(0)
            
            if text_to_speak:
                try:
                    # Use run() to wait for speech to complete before next
                    subprocess.run(
                        ["say", "-v", "Samantha", text_to_speak],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=30
                    )
                except:
                    pass
            else:
                time.sleep(0.1)
    
    def speak(self, text: str):
        """Queue text for speech (plays sequentially, never overlaps)."""
        # Clean text for speech
        text = text.replace("🎯", "").replace("🚫", "").replace("✅", "")
        text = text.replace("📑", "").replace("🔄", "").replace("⚠️", "")
        text = text.replace("⏳", "").replace("⏰", "").replace("👁️", "")
        
        with self.speech_lock:
            # Clear queue if too many pending (avoid lag)
            if len(self.speech_queue) > 2:
                self.speech_queue = self.speech_queue[-1:]
            self.speech_queue.append(text)
        
        # Start speech thread if not running
        if self.speech_thread is None or not self.speech_thread.is_alive():
            self.speech_thread = threading.Thread(target=self._speech_worker, daemon=True)
            self.speech_thread.start()
    
    def initialize(self):
        """Initialize all components."""
        print("🤖 Initializing Jarvis Agent...")
        
        try:
            print("  → Initializing wake word listener...")
            self.listener = WakeWordListener()
            
            print("  → Initializing speech-to-text...")
            self.stt = SpeechToText()
            
            print("  → Testing browser connection...")
            tabs = self.browser.get_tabs()
            print(f"  → Found {len(tabs)} browser tabs")
            
            print("✅ Jarvis Agent initialized successfully!")
            
            # Start speech thread
            self.speech_thread = threading.Thread(target=self._speech_worker, daemon=True)
            self.speech_thread.start()
            
            self.speak("Jarvis is ready. Say Jarvis followed by a command.")
            return True
            
        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            return False
    
    def parse_intent(self, command: str) -> list:
        """
        Use Gemini to parse the user's intent from natural language.
        Supports complex multi-action commands.
        
        Returns a LIST of action dicts, each with:
        - action: "focus", "switch", "open", "close", "restore", "set_goal", "pause_monitor", "resume_monitor", "status", "unknown"
        - target: specific tab/url/goal depending on action
        - goal: if setting a new focus goal
        """
        prompt = f"""You are a voice command parser for a focus/productivity assistant.

Parse this voice command and return a JSON ARRAY of actions. Complex commands may have MULTIPLE actions.

Command: "{command}"
Current Goal: "{self.current_goal}"

Possible actions:
1. "focus" - Close distracting tabs based on a goal. Example: "keep productivity apps", "focus on coding"
2. "switch" - Switch to a specific tab. Example: "go to gmail", "switch to github"
3. "open" - Open a new website. Example: "open google docs", "open gmail"
4. "close" - Close specific tabs. Example: "close youtube", "close instagram", "remove gmail"
5. "restore" - Restore previously closed tabs. Example: "restore tabs", "bring back my tabs"
6. "set_goal" - Set a new focus goal. Example: "I'm working on React", "my goal is studying"
7. "pause_monitor" - DISABLE focus mode. Example: "break time", "I'm done working", "relax mode"
8. "resume_monitor" - RE-ENABLE focus mode. Example: "back to work", "work mode"
9. "status" - Get current status. Example: "what's my goal", "status"
10. "scan" - Just list/scan tabs. Example: "what tabs do I have", "list my tabs"

IMPORTANT: A command can have MULTIPLE actions! Parse ALL of them.

Examples:
- "open google docs" -> [{{"action": "open", "target": "google docs"}}]
- "close gmail" -> [{{"action": "close", "target": "gmail"}}]
- "open google docs and close gmail" -> [{{"action": "open", "target": "google docs"}}, {{"action": "close", "target": "gmail"}}]
- "switch to github and close youtube" -> [{{"action": "switch", "target": "github"}}, {{"action": "close", "target": "youtube"}}]
- "focus on coding and open github" -> [{{"action": "focus", "target": "coding", "goal": "coding"}}, {{"action": "open", "target": "github"}}]
- "close all distractions and open google docs" -> [{{"action": "focus", "target": "productivity"}}, {{"action": "open", "target": "google docs"}}]

Output ONLY the JSON array, no explanation."""

        try:
            response = self.gemini.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            
            text = response.text.strip()
            # Remove markdown if present
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:-1])
            
            parsed = json.loads(text)
            
            # Ensure it's a list
            if isinstance(parsed, dict):
                return [parsed]
            return parsed
            
        except Exception as e:
            print(f"Intent parsing error: {e}")
            return [{"action": "unknown", "error": str(e)}]
    
    def execute_command(self, command: str):
        """Execute a voice command (supports multiple actions)."""
        print(f"\n📢 Command: \"{command}\"")
        
        # Parse intent - now returns a LIST of actions
        intents = self.parse_intent(command)
        
        print(f"   Parsed {len(intents)} action(s): {intents}")
        
        if len(intents) > 1:
            self.speak(f"Executing {len(intents)} actions.")
        
        # Execute each action in sequence
        for i, intent in enumerate(intents):
            action = intent.get("action", "unknown")
            target = intent.get("target")
            
            if len(intents) > 1:
                print(f"\n   [{i+1}/{len(intents)}] {action}: {target}")
            
            self._execute_single_action(action, target, intent)
    
    def _execute_single_action(self, action: str, target, intent: dict):
        """Execute a single action."""
        if action == "focus":
            self._handle_focus(target or "productivity")
            
        elif action == "switch":
            self._handle_switch(target)
            
        elif action == "open":
            self._handle_open(target)
            
        elif action == "close":
            self._handle_close(target)
            
        elif action == "restore":
            self._handle_restore(target)
            
        elif action == "set_goal":
            goal = intent.get("goal", target)
            self._handle_set_goal(goal)
            
        elif action == "pause_monitor":
            self.focus_mode_active = False
            self.monitoring_enabled = False
            self.warned_tabs.clear()
            self.speak("Break time. Focus mode disabled. Browse freely.")
            print("⏸️ Focus mode DISABLED - Browse freely")
            
        elif action == "resume_monitor":
            self.focus_mode_active = True
            self.monitoring_enabled = True
            self.speak("Back to work. Focus mode re-activated.")
            print("▶️ Focus mode RE-ACTIVATED")
            
        elif action == "status":
            self._handle_status()
            
        elif action == "scan":
            self._handle_scan()
            
        else:
            self.speak(f"I didn't understand part of that command.")
            print(f"❓ Unknown action: {action}")
    
    def _handle_focus(self, goal_hint: str):
        """Handle focus command - evaluate and close distracting tabs."""
        # Update goal if provided
        if goal_hint and goal_hint != "null":
            self.current_goal = goal_hint
        
        # Activate persistent focus mode
        self.focus_mode_active = True
        self.monitoring_enabled = True
        
        self.speak(f"Focus mode activated for {self.current_goal}. I will actively close any distractions.")
        print(f"🎯 FOCUS MODE ACTIVE: {self.current_goal}")
        print(f"   ⚠️ Distracting tabs will be automatically closed!")
        
        # Get tabs
        tabs = self.browser.get_tabs()
        if not tabs:
            self.speak("No tabs found.")
            return
        
        # Evaluate with AI
        tabs_for_eval = [{"id": t["id"], "title": t["title"], "url": t["url"]} for t in tabs]
        result = self.focus_manager.evaluate_tabs(tabs_for_eval, self.current_goal)
        
        # Backup and close distractions
        tabs_to_close = [t for t in tabs if t["id"] in result["tabs_to_hide"]]
        
        if not tabs_to_close:
            self.speak("All tabs look productive. No distractions found.")
            return
        
        # Backup
        self._backup_tabs(tabs_to_close)
        
        # Close (in reverse order to avoid index shifting)
        closed_count = 0
        for tab in sorted(tabs_to_close, key=lambda t: t["tab_index"], reverse=True):
            if self.browser.close_tab(tab["window_id"], tab["tab_index"]):
                closed_count += 1
                print(f"   🚫 Closed: {tab['title'][:40]}")
        
        self.speak(f"Closed {closed_count} distracting tabs. You now have {len(result['tabs_to_keep'])} productive tabs.")
    
    def _handle_switch(self, target: str):
        """Switch to a tab matching the target."""
        if not target:
            self.speak("Which tab should I switch to?")
            return
        
        result = self.browser.switch_to_tab_by_keyword(target)
        print(f"   {result}")
        
        if "Switched to" in result:
            self.speak(f"Switched to {target}")
        else:
            self.speak(f"Could not find a tab matching {target}")
    
    def _handle_open(self, target: str):
        """Open a URL."""
        if not target:
            self.speak("What website should I open?")
            return
        
        target_lower = target.lower().strip()
        
        # Check if it's a known site name
        if target_lower in self.SITE_URLS:
            url = self.SITE_URLS[target_lower]
        elif target.startswith("http"):
            url = target
        elif "." in target:
            # Looks like a URL
            url = f"https://{target}"
        else:
            # Check partial matches in SITE_URLS
            matched_url = None
            for site_name, site_url in self.SITE_URLS.items():
                if target_lower in site_name or site_name in target_lower:
                    matched_url = site_url
                    break
            
            if matched_url:
                url = matched_url
            else:
                # Last resort: add .com
                url = f"https://{target_lower.replace(' ', '')}.com"
        
        # Check if opening a distraction while in focus mode
        if self.focus_mode_active and self._is_distraction(url, target):
            self.speak(f"You're in focus mode. {target} is a distraction. Say 'break time' first to access it.")
            print(f"   🚫 Blocked distraction: {target}")
            return
        
        success = self.browser.open_url(url, new_tab=True)
        if success:
            self.speak(f"Opening {target}")
            print(f"   🌐 Opened: {url}")
        else:
            self.speak(f"Could not open {target}")
    
    def _handle_close(self, target: str):
        """Close tabs matching target."""
        if not target:
            self.speak("Which tab should I close?")
            return
        
        tabs = self.browser.get_tabs()
        target_lower = target.lower()
        
        closed = 0
        for tab in sorted(tabs, key=lambda t: t["tab_index"], reverse=True):
            if target_lower in tab["title"].lower() or target_lower in tab["url"].lower():
                self._backup_tabs([tab])
                if self.browser.close_tab(tab["window_id"], tab["tab_index"]):
                    closed += 1
                    print(f"   🚫 Closed: {tab['title'][:40]}")
        
        if closed:
            self.speak(f"Closed {closed} tabs matching {target}")
        else:
            self.speak(f"No tabs found matching {target}")
    
    def _handle_restore(self, target: str = None):
        """Restore tabs from backup."""
        backup = self._load_backup()
        
        if not backup:
            self.speak("No tabs to restore.")
            return
        
        # If target specified, filter
        if target:
            target_lower = target.lower()
            backup = [t for t in backup if target_lower in t.get("title", "").lower() 
                     or target_lower in t.get("url", "").lower()]
        
        if not backup:
            self.speak(f"No backed up tabs matching {target}")
            return
        
        restored = 0
        for tab in backup[-5:]:  # Restore last 5
            if self.browser.open_url(tab["url"], new_tab=True):
                restored += 1
                print(f"   ✅ Restored: {tab['title'][:40]}")
        
        self.speak(f"Restored {restored} tabs")
        
        # Clear restored from backup
        remaining = self._load_backup()[:-restored] if restored else []
        with open(self.BACKUP_FILE, "w") as f:
            json.dump(remaining, f)
    
    def _handle_set_goal(self, goal: str):
        """Set a new focus goal."""
        if goal:
            self.current_goal = goal
            self.speak(f"Goal set to: {goal}. I'll help you stay focused.")
            print(f"🎯 New goal: {goal}")
        else:
            self.speak(f"Your current goal is: {self.current_goal}")
    
    def _handle_status(self):
        """Report current status."""
        tabs = self.browser.get_tabs()
        
        if self.focus_mode_active:
            mode = "Focus mode is ACTIVE. Distractions will be closed automatically."
        else:
            mode = "Focus mode is OFF. You can browse freely."
        
        status = f"Goal: {self.current_goal}. {len(tabs)} tabs open. {mode}"
        self.speak(status)
        print(f"\n📊 STATUS:")
        print(f"   🎯 Goal: {self.current_goal}")
        print(f"   📑 Tabs: {len(tabs)}")
        print(f"   🛡️ Focus Mode: {'ACTIVE' if self.focus_mode_active else 'OFF'}")
        print(f"   👁️ Monitoring: {'ON' if self.monitoring_enabled else 'OFF'}")
    
    def _handle_scan(self):
        """Scan and report tabs."""
        tabs = self.browser.get_tabs()
        
        if not tabs:
            self.speak("No tabs found.")
            return
        
        print(f"\n📑 Found {len(tabs)} tabs:")
        for tab in tabs:
            print(f"   [{tab['id']}] {tab['title'][:50]}")
        
        self.speak(f"You have {len(tabs)} tabs open. Check the console for the full list.")
    
    def _backup_tabs(self, tabs: list):
        """Backup tabs before closing."""
        backup = self._load_backup()
        
        for tab in tabs:
            backup.append({
                "title": tab["title"],
                "url": tab["url"],
                "closed_at": datetime.now().isoformat()
            })
        
        with open(self.BACKUP_FILE, "w") as f:
            json.dump(backup, f, indent=2)
    
    def _load_backup(self) -> list:
        """Load backup file."""
        if os.path.exists(self.BACKUP_FILE):
            try:
                with open(self.BACKUP_FILE, "r") as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def _is_distraction(self, url: str, title: str) -> bool:
        """Check if a tab is a distraction based on patterns and current goal."""
        url_lower = url.lower()
        title_lower = title.lower()
        goal_lower = self.current_goal.lower()
        
        # If the tab matches the current goal, it's NOT a distraction
        goal_keywords = goal_lower.replace(",", " ").replace(".", " ").split()
        for keyword in goal_keywords:
            if len(keyword) > 3 and (keyword in url_lower or keyword in title_lower):
                return False
        
        # Check if it's a known productivity site
        for pattern in self.PRODUCTIVITY_PATTERNS:
            if pattern in url_lower or pattern in title_lower:
                return False
        
        # Check if it's a known distraction
        for pattern in self.DISTRACTION_PATTERNS:
            if pattern in url_lower or pattern in title_lower:
                return True
        
        # If not in either list, assume it's okay (not a known distraction)
        return False
    
    def _get_active_tab(self) -> Optional[dict]:
        """Get the currently active/frontmost tab using AppleScript."""
        try:
            # Use AppleScript to get the active tab specifically
            script = '''
            tell application "Google Chrome"
                set activeTab to active tab of front window
                set tabTitle to title of activeTab
                set tabURL to URL of activeTab
                return tabTitle & "|||" & tabURL
            end tell
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and "|||" in result.stdout:
                parts = result.stdout.strip().split("|||")
                if len(parts) >= 2:
                    return {
                        "title": parts[0],
                        "url": parts[1],
                        "window_id": 1,
                        "tab_index": 1  # Will need to find actual index
                    }
        except:
            pass
        return None
    
    def _close_active_tab(self):
        """Close the currently active tab."""
        try:
            script = '''
            tell application "Google Chrome"
                close active tab of front window
            end tell
            '''
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            return True
        except:
            return False
    
    def _monitor_loop(self):
        """Background monitoring loop - actively closes distractions when focus mode is on."""
        print("👁️ Starting distraction monitor...")
        
        while self.running:
            try:
                # Only monitor when focus mode is active
                if not self.focus_mode_active or not self.monitoring_enabled:
                    time.sleep(self.MONITOR_INTERVAL)
                    continue
                
                # Get the ACTIVE (frontmost) tab
                current_tab = self._get_active_tab()
                
                if not current_tab:
                    time.sleep(self.MONITOR_INTERVAL)
                    continue
                
                url = current_tab["url"]
                title = current_tab["title"]
                
                # Skip if same as last check (no change)
                if url == self.last_active_url:
                    # But check if we're waiting on a warning
                    if url in self.warned_tabs:
                        elapsed = time.time() - self.warned_tabs[url]
                        if elapsed >= self.WARNING_COUNTDOWN:
                            # Time's up - close it!
                            print(f"⏰ AUTO-CLOSING: {title[:40]}")
                            self.speak("Time's up. Closing distraction now.")
                            self._backup_tabs([current_tab])
                            self._close_active_tab()
                            del self.warned_tabs[url]
                            self.last_active_url = None
                    time.sleep(1)  # Check more frequently when warning active
                    continue
                
                self.last_active_url = url
                
                # Check if this is a distraction
                if self._is_distraction(url, title):
                    if url not in self.warned_tabs:
                        # First time seeing this distraction - warn!
                        self.warned_tabs[url] = time.time()
                        print(f"\n⚠️ DISTRACTION DETECTED: {title[:50]}")
                        print(f"   URL: {url[:60]}")
                        print(f"   ⏳ Closing in {self.WARNING_COUNTDOWN} seconds...")
                        self.speak(f"Warning! {title[:25]} is a distraction. Closing in 3 seconds. Switch away to cancel.")
                else:
                    # Not a distraction - clear any warnings for this URL
                    if url in self.warned_tabs:
                        print(f"✅ Switched to productive tab: {title[:40]}")
                        del self.warned_tabs[url]
                
                time.sleep(self.MONITOR_INTERVAL)
                
            except Exception as e:
                print(f"Monitor error: {e}")
                time.sleep(self.MONITOR_INTERVAL)
    
    def _voice_loop(self):
        """Main voice command loop."""
        print("\n🎤 Voice control active. Say 'Jarvis' followed by a command.")
        print("   Examples:")
        print("   - 'Jarvis, focus on coding'")
        print("   - 'Jarvis, switch to gmail'")
        print("   - 'Jarvis, close youtube'")
        print("   - 'Jarvis, open github.com'")
        print("   - 'Jarvis, restore my tabs'")
        print("   - 'Jarvis, pause monitoring'")
        print("")
        
        while self.running:
            try:
                # Wait for wake word
                print("🎤 Listening for 'Jarvis'...")
                detected = self.listener.listen()
                
                if detected and self.running:
                    print("✨ Wake word detected!")
                    self.speak("Yes?")
                    
                    # Listen for command
                    result = self.stt.listen_and_transcribe()
                    
                    if result and result.get("text"):
                        command = result["text"]
                        self.execute_command(command)
                    else:
                        print("❓ Could not understand command")
                        
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Voice loop error: {e}")
                time.sleep(1)
    
    def run(self):
        """Start the agent."""
        if not self.initialize():
            return
        
        # Start monitor thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        # Run voice loop in main thread
        try:
            self._voice_loop()
        except KeyboardInterrupt:
            print("\n\n👋 Shutting down Jarvis...")
        finally:
            self.running = False
            self.speech_running = False
            if self.listener:
                self.listener.cleanup()
            print("Goodbye!")


def main():
    """Entry point."""
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║            🤖 JARVIS - Voice-Controlled Focus Agent            ║
    ╠════════════════════════════════════════════════════════════════╣
    ║                                                                ║
    ║  Say "Jarvis" followed by:                                     ║
    ║                                                                ║
    ║  🛡️ FOCUS MODE (actively closes distractions):                 ║
    ║     • "focus on coding" / "stay focused on Google Docs"        ║
    ║     • "keep productivity apps only"                            ║
    ║                                                                ║
    ║  🌐 TAB CONTROL:                                               ║
    ║     • "switch to gmail" / "go to github"                       ║
    ║     • "open google docs" / "open github.com"                   ║
    ║     • "close youtube" / "close instagram"                      ║
    ║     • "restore tabs" - bring back closed tabs                  ║
    ║                                                                ║
    ║  ⏸️ BREAK TIME (disables focus mode):                          ║
    ║     • "break time" / "I'm done working"                        ║
    ║     • "back to work" - re-enables focus mode                   ║
    ║                                                                ║
    ║  ⚠️  When focus mode is ON, opening a distraction triggers     ║
    ║      a 3-second warning, then auto-closes the tab!             ║
    ║                                                                ║
    ║  Press Ctrl+C to exit                                          ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    agent = JarvisAgent()
    agent.run()


if __name__ == "__main__":
    main()

