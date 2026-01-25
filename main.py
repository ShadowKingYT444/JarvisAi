"""Jarvis Agent - Fully Voice-Controlled Focus Assistant (Windows/macOS)
No buttons needed - pure voice control with 24/7 distraction monitoring.
"""

import os
import sys
import json
import time
import threading
import argparse
import re
from typing import Optional

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, pyqtSignal

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Local imports
from wakeword.listener import WakeWordListener
from wakeword.stt import SpeechToText
from platforms import get_browser_control
from tts_manager import get_tts_provider
from focus_manager import FocusManager
from jarvis_ui import JarvisOverlay

def remove_filler_words(text: str) -> str:
    """Removes common filler words from the input text."""
    fillers = [
        r"\bum\b", r"\buh\b", r"\bah\b", r"\bmm\b", r"\bhm\b", r"\bhmm\b", 
        r"\blike\b", r"\bactually\b", r"\bbasically\b", r"\bliterally\b",
        r"\bstuttering\b"
    ]
    cleaned_text = text
    for filler in fillers:
        # Remove filler + optional following comma
        cleaned_text = re.sub(filler + r"\s*,?", "", cleaned_text, flags=re.IGNORECASE)
    
    # Clean up multiple spaces and leading/trailing punctuation/whitespace
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip(" ,.")
    return cleaned_text

class JarvisAgent:
    """Logic controller for Jarvis."""
    
    BACKUP_FILE = "session_backup.json"
    MONITOR_INTERVAL = 2
    WARNING_COUNTDOWN = 3
    
    # 1. Hardcoded Sites (Top 100+ to prevent hallucinations)
    SITE_URLS = {
        # Social
        "facebook": "https://facebook.com", "instagram": "https://instagram.com",
        "twitter": "https://twitter.com", "x": "https://x.com",
        "linkedin": "https://linkedin.com", "tiktok": "https://tiktok.com",
        "reddit": "https://reddit.com", "pinterest": "https://pinterest.com",
        "snapchat": "https://snapchat.com", "discord": "https://discord.com",
        "whatsapp": "https://web.whatsapp.com", "telegram": "https://web.telegram.org",
        # Video/Ent
        "youtube": "https://youtube.com", "netflix": "https://netflix.com",
        "twitch": "https://twitch.tv", "hulu": "https://hulu.com",
        "disney": "https://disneyplus.com", "prime video": "https://primevideo.com",
        "spotify": "https://open.spotify.com", "hbomax": "https://max.com",
        # Productivity
        "gmail": "https://mail.google.com", "email": "https://mail.google.com",
        "outlook": "https://outlook.live.com", "yahoo mail": "https://mail.yahoo.com",
        "google drive": "https://drive.google.com", "drive": "https://drive.google.com",
        "google docs": "https://docs.google.com", "docs": "https://docs.google.com",
        "google sheets": "https://sheets.google.com", "sheets": "https://sheets.google.com",
        "google slides": "https://slides.google.com",
        "notion": "https://notion.so", "trello": "https://trello.com",
        "asana": "https://asana.com", "monday": "https://monday.com",
        "slack": "https://slack.com", "zoom": "https://zoom.us",
        "github": "https://github.com", "gitlab": "https://gitlab.com",
        "bitbucket": "https://bitbucket.org", "stackoverflow": "https://stackoverflow.com",
        "chatgpt": "https://chat.openai.com", "claude": "https://claude.ai",
        "gemini": "https://gemini.google.com", "bard": "https://gemini.google.com",
        "wikipedia": "https://wikipedia.org",
        # Shopping
        "amazon": "https://amazon.com", "ebay": "https://ebay.com",
        "walmart": "https://walmart.com", "etsy": "https://etsy.com",
        "aliexpress": "https://aliexpress.com", "target": "https://target.com",
        # News
        "cnn": "https://cnn.com", "bbc": "https://bbc.com",
        "nytimes": "https://nytimes.com", "fox news": "https://foxnews.com",
        "forbes": "https://forbes.com", "bloomberg": "https://bloomberg.com",
        # Tech
        "apple": "https://apple.com", "microsoft": "https://microsoft.com",
        "google": "https://google.com", "bing": "https://bing.com",
        "duckduckgo": "https://duckduckgo.com",
        # Education
        "khan academy": "https://khanacademy.org", "coursera": "https://coursera.org",
        "udemy": "https://udemy.com", "edx": "https://edx.org",
        "quizlet": "https://quizlet.com",
    }
    
    DISTRACTION_PATTERNS = [
        "youtube.com/watch", "netflix.com", "twitch.tv", "tiktok.com",
        "instagram.com", "facebook.com", "x.com", "twitter.com", 
        "reddit.com", "9gag.com", "imgur.com", "discord.com",
        "amazon.com", "ebay.com"
    ]

    def __init__(self, use_voice=True):
        self.listener = None
        self.stt = None
        self.browser = get_browser_control()
        self.tts = get_tts_provider()
        self.focus_manager = FocusManager()
        self.use_voice = use_voice
        
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
             # Fallback if somehow missing
             api_key = "AIzaSyCZi6VSgl4TAKxjyKBT83v906UGOxgmxRQ"
             
        self.gemini = genai.Client(api_key=api_key)
        self.model = "gemini-2.0-flash-exp"
        
        self.current_goal = "General productivity"
        self.focus_mode_active = False
        self.monitoring_enabled = True
        self.running = True
        self.warned_tabs = {}
        self.speech_process = None
        self.speech_lock = threading.Lock()

    def initialize(self):
        print("🤖 Initializing Jarvis Agent...")
        try:
            if self.use_voice:
                self.listener = WakeWordListener()
                self.stt = SpeechToText()
            print(f"✅ Jarvis Agent initialized!")
            
            # Initial TTS
            self.tts.set_voice_persona("jarvis")
            self.speak("Systems online.")
            return True
        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            return False

    def speak(self, text: str):
        self.tts.speak(text)

    def parse_intent(self, command: str) -> list:
        # Improved Prompt for robustness
        prompt = f"""User Command: "{command}"
        
        Task: specific actions to JSON list.
        Available Actions: 
        1. focus (target=goal) -> Start blocking distractions
        2. pause_monitor (no target) -> Stop blocking (user says break/relax/stop)
        3. open (target=site/url) -> Open a website
        4. close (target=name) -> Close a tab
        5. ask (target=question) -> Just answer the user's question (Chat)
        6. search (target=query) -> Google search
        
        Rules:
        - If multiple steps (e.g. "open X and Y"), return multiple objects.
        - "Google Doc" -> target="google docs"
        - "Youtube" -> target="youtube"
        - IF INPUT IS MEANINGLESS (e.g. "you", "um", "ah", <3 chars), RETURN EMPTY LIST [].
        
        Return JSON Array ONLY:
        Example: [{{"action":"open","target":"google"}}, {{"action":"focus","target":"coding"}}]
        """
        try:
            response = self.gemini.models.generate_content(
                model=self.model, contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            text = response.text.strip()
            print(f"\n🧠 Gemini Raw Output: {text}") # VERBOSE LOGGING
            if text.startswith("```"): text = "\n".join(text.split("\n")[1:-1])
            parsed = json.loads(text)
            return [parsed] if isinstance(parsed, dict) else parsed
        except Exception as e:
            print(f"Intent parsing error: {e}")
            return []

    def get_dynamic_distractions(self, goal: str) -> list:
        """Ask Gemini which sites to block based on the goal."""
        default = self.DISTRACTION_PATTERNS
        prompt = f"""User Goal: "{goal}"
        
        Task: Identify which websites from the list below should be BLOCKED as distractions for this goal.
        Default Blocklist: {json.dumps(default)}
        
        Rules:
        - If the goal is "Relaxing" or "Watching videos", maybe unblock YouTube/Netflix.
        - If the goal is "Coding", keep social media blocked.
        - You can add common distractions if relevant (e.g. "news.ycombinator.com" if goal is "studying").
        
        Return JSON List of strings to BLOCK:
        Example: ["youtube.com", "facebook.com"]
        """
        try:
            response = self.gemini.models.generate_content(
                model=self.model, contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            text = response.text.strip()
            print(f"\n🧠 Gemini Blocking Strategy: {text}")
            if text.startswith("```"): text = "\n".join(text.split("\n")[1:-1])
            return json.loads(text)
        except:
            return default
            
    def answer_general_question(self, question: str):
        """Ask Gemini a question and speak the answer as Soren/Alexa."""
        print(f"🤔 Soren Pondering: {question}")
        try:
            # User requested 3.0, we use the absolute latest available experimental pro model.
            soren_model = "gemini-2.0-flash-exp" 
            
            system_prompt = "You are Alyssa (also known as Soren), a helpful, flirtatious, and intelligent AI assistant. Keep answers concise (MAXIMUM 100 WORDS) and spoken-word friendly."
            response = self.gemini.models.generate_content(
                model=soren_model,
                contents=f"{system_prompt}\nUser Question: {question}",
                config=types.GenerateContentConfig(temperature=0.7)
            )
            answer = response.text.strip()
            self.tts.set_voice_persona("soren")
            self.speak(answer)
            # CRITICAL: Wait for speech to finish so we don't listen to ourselves
            self.tts.wait()
        except Exception as e:
            print(f"Soren Error: {e}")
            self.tts.set_voice_persona("soren")
            self.speak("I'm having trouble thinking right now, daddy.")
            self.tts.wait()

    # ... (rest of class)

    def execute_command(self, command: str):
        print(f"\n📢 Command: \"{command}\" ")
        
        # KEYWORD SHORTCUTS
        cmd_lower = command.lower()
        if "break" in cmd_lower or "relax" in cmd_lower or "chill" in cmd_lower or "stop mode" in cmd_lower:
             self._execute_single_action("pause_monitor", None)
             return
             
        intents = self.parse_intent(command)
        
        # LOGIC FIX: Don't say "Yes sir" if we are asking Soren a question
        is_question = any(i.get("action") == "ask" for i in intents)
        
        if intents and len(intents) > 0 and not is_question:
            self.tts.set_voice_persona("jarvis")
            self.speak("Yes, sir.")
            self.tts.wait()

        for intent in intents:
            action = intent.get("action", "unknown")
            target = intent.get("target")
            self._execute_single_action(action, target)
    
    def _execute_single_action(self, action, target):
        if action == "focus": 
            # Ask for clarification if target is vague or generic
            vague_targets = ["productivity", "work", "focus", "focus mode", "start focus", "goal", "my goal"]
            if not target or target.lower() in vague_targets:
                self.tts.set_voice_persona("jarvis")
                self.speak("What is the current task, sir?")
                self.tts.wait()
                
                # Listen for answer
                if self.use_voice:
                    response = self.stt.listen_and_transcribe()
                    if response and response.get("text"):
                        target = response["text"]
                else:
                    print(">> (Type your goal):")
                    target = sys.stdin.readline().strip()
            
            self._handle_focus(target)
            
        elif action == "open": self._handle_open(target)
        elif action == "close": self._handle_close(target)
        elif action == "pause_monitor": 
            self.focus_mode_active = False
            self.tts.set_voice_persona("jarvis")
            self.speak("Break mode engaged. Relax, sir.")
            self._handle_restore()
        elif action == "ask":
            self.answer_general_question(target)
        elif action == "search":
             url = f"https://google.com/search?q={target.replace(' ', '+')}"
             self.browser.open_url(url)
        else: print(f"Unknown action: {action}")

    def _handle_focus(self, target):
        self.current_goal = target or "productivity"
        self.focus_mode_active = True
        self.tts.set_voice_persona("jarvis")
        
        # Don't read out "Goal:goal" awkwardly. Make it natural.
        self.speak(f"Focus mode enabled. Targeting: {self.current_goal}")
        self.tts.wait()
        
        # AI-Driven Filters
        patterns = self.get_dynamic_distractions(self.current_goal)
        
        print(f"[ACTION] Initiating Distraction Sweep...")
        self.browser.scour_tabs(patterns)
        self.tts.set_voice_persona("jarvis")
        self.speak("Workspace sanitized.")
        self.tts.wait()

    def _handle_open(self, target):
        if not target: return
        url = self.SITE_URLS.get(target.lower())
        
        if not url:
            if "." not in target:
                 url = f"https://{target.replace(' ', '')}.com"
            else:
                 url = target
                 
        if not url.startswith("http"): url = "https://" + url
        self.browser.open_url(url)

    def _handle_close(self, target):
        self.browser.close_active_tab()

    def _handle_restore(self):
        pass

    def start_monitor(self):
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def _monitor_loop(self):
        print("👁️ Monitor started")
        while self.running:
            try:
                if self.focus_mode_active and self.monitoring_enabled:
                    current = self.browser.get_active_tab()
                    if current:
                        url = current["url"]
                        title = current["title"]
                        
                        is_distraction = False
                        for p in self.DISTRACTION_PATTERNS:
                            if p in url.lower() or p in title.lower():
                                is_distraction = True
                                break
                        
                        if is_distraction:
                             if url not in self.warned_tabs:
                                 self.warned_tabs[url] = time.time()
                                 self.tts.set_voice_persona("jarvis")
                                 self.speak("Stay focused.")
                             elif time.time() - self.warned_tabs[url] > self.WARNING_COUNTDOWN:
                                 self.browser.close_active_tab()
                                 del self.warned_tabs[url]
                        else:
                             if url in self.warned_tabs: del self.warned_tabs[url]
                                
                time.sleep(self.MONITOR_INTERVAL)
            except Exception as e:
                print(f"⚠️ Monitor Loop Error: {e}")
                time.sleep(self.MONITOR_INTERVAL)

class VoiceWorker(QThread):
    sig_wake_jarvis = pyqtSignal()
    sig_wake_soren = pyqtSignal()
    sig_sleep = pyqtSignal()
    
    def __init__(self, agent):
        super().__init__()
        self.agent = agent
        self.running = True

    def run(self):
        print("🎤 Voice thread started.")
        while self.running:
            try:
                # 1. Listen for ID (0=Jarvis, 1=Alexa/Soren)
                keyword_index = self.agent.listener.listen()
                
                if keyword_index >= 0 and self.running:
                    print(f"✨ Wake Word Detected! Index: {keyword_index}")
                    
                    if keyword_index == 0:
                        # JARVIS MODE
                        self.agent.tts.set_voice_persona("jarvis")
                        self.agent.speak("Yes?")
                        self.sig_wake_jarvis.emit()
                        self.agent.tts.wait()
                    else:
                        # SOREN MODE
                        self.agent.tts.set_voice_persona("soren")
                        self.agent.speak("Yes daddy?")
                        self.sig_wake_soren.emit()
                        self.agent.tts.wait()
                    
                    # 2. Listen for Command/Question
                    result = self.agent.stt.listen_and_transcribe()
                    self.sig_sleep.emit()
                    
                    if result and result.get("text"):
                        text = result["text"]
                        
                        if keyword_index == 0:
                            # Jarvis: Execute Command
                            self.agent.execute_command(text)
                        else:
                            # Soren: Answer Question
                            self.agent.answer_general_question(text)
                    
            except Exception as e:
                print(f"Error in voice loop: {e}")
                time.sleep(1)

class TextWorker(QThread):
    sig_wake_jarvis = pyqtSignal()
    sig_wake_soren = pyqtSignal()
    sig_sleep = pyqtSignal()

    def __init__(self, agent):
        super().__init__()
        self.agent = agent
        self.running = True

    def run(self):
        print("⌨️ Text thread started. Type 'Jarvis, <command>' or 'Soren, <question>'")
        while self.running:
            try:
                # Read from stdin (blocking)
                raw_input = sys.stdin.readline().strip()
                if not raw_input:
                    continue
                
                # Check for exit
                if raw_input.lower() in ["exit", "quit"]:
                    self.running = False
                    QApplication.quit()
                    break

                # Determine persona based on prefix
                # Default to Jarvis if no prefix
                text = raw_input
                keyword_index = 0 # Default Jarvis

                if raw_input.lower().startswith("soren") or raw_input.lower().startswith("alexa"):
                    keyword_index = 1
                    # Remove prefix
                    text = re.sub(r"^(soren|alexa)[,\s]*", "", raw_input, flags=re.IGNORECASE)
                elif raw_input.lower().startswith("jarvis"):
                    keyword_index = 0
                    # Remove prefix
                    text = re.sub(r"^jarvis[,\s]*", "", raw_input, flags=re.IGNORECASE)
                
                # Filler Word Removal
                text = remove_filler_words(text)
                print(f"📝 Processed Input: '{text}'")

                if keyword_index == 0:
                    # JARVIS MODE
                    self.agent.tts.set_voice_persona("jarvis")
                    # self.agent.speak("Yes?") # Optional in text mode to be less noisy? But requested in specs.
                    self.sig_wake_jarvis.emit()
                    
                    # Execute
                    self.agent.execute_command(text)
                else:
                    # SOREN MODE
                    self.agent.tts.set_voice_persona("soren")
                    # self.agent.speak("Yes?")
                    self.sig_wake_soren.emit()
                    
                    # Answer
                    self.agent.answer_general_question(text)
                
                self.sig_sleep.emit()

            except Exception as e:
                print(f"Error in text loop: {e}")
                time.sleep(1)

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="Jarvis AI Agent")
    parser.add_argument("--test", "--text", action="store_true", help="Run in text/test mode")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    print("--- JARVIS STARTING ---")
    
    agent = JarvisAgent(use_voice=not args.test)
    if not agent.initialize():
        sys.exit(1)
        
    overlay = JarvisOverlay()
    
    if args.test:
        worker = TextWorker(agent)
    else:
        worker = VoiceWorker(agent)
    
    worker.sig_wake_jarvis.connect(overlay.wake_up)
    worker.sig_wake_soren.connect(overlay.wake_up)
    worker.sig_sleep.connect(overlay.sleep)
    
    agent.start_monitor()
    worker.start()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
