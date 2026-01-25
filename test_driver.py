import sys
import io
import time
import unittest
from unittest.mock import MagicMock, patch
from contextlib import redirect_stdout

# Add current directory to path
sys.path.append(".")

# Import from main
from main import JarvisAgent, remove_filler_words
import tts_manager

# Mock TTS
class MockTTS:
    def __init__(self):
        self.last_spoken = ""
        
    def speak(self, text: str):
        self.last_spoken = text
        print(f"[MOCK TTS] Speaking: {text}")
        
    def set_voice_persona(self, persona: str):
        print(f"[MOCK TTS] Persona set to: {persona}")

    def wait(self):
        pass

class TestJarvis(unittest.TestCase):
    
    def setUp(self):
        # Suppress standard output during initialization to keep logs clean
        self.agent = JarvisAgent(use_voice=False)
        self.agent.tts = MockTTS()
        # Mock browser to avoid spamming tabs, but log calls
        self.agent.browser = MagicMock()
        self.agent.browser.open_url = MagicMock(side_effect=lambda url: print(f"[MOCK BROWSER] Opening: {url}"))
        self.agent.browser.close_active_tab = MagicMock(side_effect=lambda: print(f"[MOCK BROWSER] Closing tab"))
        self.agent.browser.scour_tabs = MagicMock(side_effect=lambda patterns: print(f"[MOCK BROWSER] Scouring tabs: {patterns}"))
        
        self.agent.initialize()

    def test_01_filler_removal(self):
        print("\n--- Test 1: Filler Removal & Navigation ---")
        raw_input = "Um, Jarvis, open Google"
        
        # 1. Verify Filler Removal
        clean_input = remove_filler_words(raw_input)
        # Expected: "Jarvis, open Google"
        # The function `remove_filler_words` in main.py only removes specific words.
        # "Um" is in the list. "Jarvis" is NOT a filler word, it's the wake word.
        # But my text loop in main.py handles the wake word stripping separately.
        # Here we test the function itself.
        
        print(f"Raw: '{raw_input}' -> Clean: '{clean_input}'")
        self.assertNotIn("Um", clean_input)
        
        # 2. Simulate Command Execution
        # We need to strip "Jarvis," manually as the TextWorker does
        command = clean_input.replace("Jarvis,", "").strip()
        self.agent.execute_command(command)
        
        # Verify Action
        # "open Google" -> should call open_url with google.com
        self.agent.browser.open_url.assert_called()
        args, _ = self.agent.browser.open_url.call_args
        self.assertIn("google.com", args[0])
        
    def test_02_focus_mode_interaction(self):
        print("\n--- Test 2: Focus Mode Interaction ---")
        command = "Turn on focus mode"
        
        # We need to simulate user input for the follow-up question
        # execute_command calls sys.stdin.readline()
        
        with patch('sys.stdin', io.StringIO("Coding\n")):
            self.agent.execute_command(command)
            
        # Verify prompts
        # 1. Agent asks "What is the current task?"
        # 2. Agent confirms "Focus mode enabled. Targeting: Coding"
        # Since we only track last_spoken in MockTTS, we might miss the first one if not careful.
        # But we can check if scour_tabs was called, which happens after confirmation.
        
        self.agent.browser.scour_tabs.assert_called()
        self.assertTrue(self.agent.focus_mode_active)
        self.assertEqual(self.agent.current_goal, "Coding")

    def test_03_break_mode(self):
        print("\n--- Test 3: Break Mode ---")
        self.agent.focus_mode_active = True
        self.agent.execute_command("Jarvis, take a break")
        
        self.assertFalse(self.agent.focus_mode_active)
        self.assertIn("Break mode engaged", self.agent.tts.last_spoken)

    def test_04_alexa_knowledge(self):
        print("\n--- Test 4: Alexa/Soren Knowledge ---")
        question = "What is the capital of France?"
        
        self.agent.answer_general_question(question)
        
        answer = self.agent.tts.last_spoken
        print(f"Answer: {answer}")
        self.assertIn("Paris", answer)
        
        # Check constraints: Under 100 words
        word_count = len(answer.split())
        print(f"Word count: {word_count}")
        self.assertLess(word_count, 100)

if __name__ == '__main__':
    # Force UTF-8 for Windows console
    sys.stdout.reconfigure(encoding='utf-8')
    unittest.main()
