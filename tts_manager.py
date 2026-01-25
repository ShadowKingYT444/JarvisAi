"""
Cross-platform Text-to-Speech Manager.
Abstacts 'say' (macOS) and 'powershell' (Windows).
"""

import platform
import subprocess
import threading
import queue
import time
import os

class TTSProvider:
    def speak(self, text: str):
        raise NotImplementedError
    
    def set_voice_persona(self, persona: str):
        pass
    
    def stop(self):
        pass

    def wait(self):
        pass

class MacOSTTS(TTSProvider):
    def __init__(self):
        self.process = None
        self.voice = "Samantha" 
        
    def set_voice_persona(self, persona: str):
        if persona == "soren":
            self.voice = "Victoria"
        else:
            self.voice = "Samantha"

    def speak(self, text: str):
        text = self._clean(text)
        self.stop()
        try:
            self.process = subprocess.Popen(
                ["say", "-v", self.voice, "-r", "190", text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except: pass
        
    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process = None
    
    def wait(self):
        if self.process:
            self.process.wait()

    def _clean(self, text):
        return text.replace("🎯", "").replace("🚫", "").replace("✅", "")

import requests
import pygame
import os

# Initialize pygame mixer for ElevenLabs audio
try:
    pygame.mixer.init()
except: pass

class WindowsTTS(TTSProvider):
    def __init__(self):
        self.queue = queue.Queue()
        self.current_persona = "jarvis"
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
        self.eleven_key = os.getenv("ELEVENLABS_API_KEY")
        # Pre-defined Voice IDs (You can change these)
        # Nicole (Female): piTKgcLEGmPE4e6mEKli
        # Antoni (Male): ErXwobaYiN019PkySvjV 
        self.eleven_voice_id = "piTKgcLEGmPE4e6mEKli" 

    def set_voice_persona(self, persona: str):
        self.current_persona = persona
    
    def _run_loop(self):
        print("[TTS] Hybrid Thread started.")
        
        while True:
            item = self.queue.get()
            if item is None: break 
            
            text, should_stop, persona = item
            
            if should_stop:
                try: pygame.mixer.stop()
                except: pass
                continue
                
            if text:
                print(f"[TTS] Speaking: '{text}' as {persona}")
                
                # URGERT FIX: Use VBScript for Jarvis (Speed)
                # Use ElevenLabs for Soren (Quality)
                # OPTIMIZATION: Use Local for short acknowledgments to be snappy
                if persona == "soren" and self.eleven_key and len(text) > 15:
                    self._speak_elevenlabs(text)
                else:
                    self._speak_vbscript(text, persona)
            
            self.queue.task_done()

    def _speak_vbscript(self, text, persona):
        try:
            # Escape quotes
            safe_text = text.replace('"', " ")
            subprocess.run(
                ["cscript", "//Nologo", "tts.vbs", safe_text, persona],
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
        except Exception as e:
            print(f"[TTS] VBS Error: {e}")

    def _speak_elevenlabs(self, text):
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.eleven_voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.eleven_key
            }
            data = {
                "text": text,
                "model_id": "eleven_turbo_v2",
                "voice_settings": {"stability": 0.7, "similarity_boost": 0.75}
            }
            
            response = requests.post(url, json=data, headers=headers)
            if response.status_code == 200:
                with open("temp_speech.mp3", "wb") as f:
                    f.write(response.content)
                
                pygame.mixer.music.load("temp_speech.mp3")
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                pygame.mixer.music.unload()
                return # SUCCESS - Do not fallback
            else:
                print(f"[TTS] ElevenLabs Failed ({response.status_code}). Fallback to Local.")
                self._speak_vbscript(text, "soren")
                
        except Exception as e:
            print(f"[TTS] ElevenLabs Error: {e}")
            self._speak_vbscript(text, "soren")

    def speak(self, text: str):
        self.queue.put((text, False, self.current_persona))

    def stop(self):
        with self.queue.mutex:
            self.queue.queue.clear()
        try: pygame.mixer.music.stop()
        except: pass

    def wait(self):
        self.queue.join()

class DummyTTS(TTSProvider):
    def speak(self, text: str):
        print(f"[DummyTTS] Speaking: {text}")

def get_tts_provider():
    system = platform.system()
    if system == "Windows":
        return WindowsTTS()
    elif system == "Darwin":
        return MacOSTTS()
    else:
        print(f"Warning: TTS not supported on {system}. Using fallback.")
        return DummyTTS()
