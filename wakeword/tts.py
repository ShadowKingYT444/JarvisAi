import os
from elevenlabs.client import ElevenLabs
from elevenlabs import play, stream
from dotenv import load_dotenv

load_dotenv()

class VoiceSynthesizer:
    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            print("Warning: Missing ELEVENLABS_API_KEY. TTS will be disabled.")
            self.client = None
        else:
            self.client = ElevenLabs(api_key=self.api_key)
            
        # Hardcoded 'Rachel' voice or similar default
        self.voice_id = "21m00Tcm4TlvDq8ikWAM" 

    def speak(self, text: str):
        """Synthesize and play speech."""
        if not self.client:
            print(f"[TTS Mock] {text}")
            return

        try:
            print(f"[TTS] Speaking: {text}")
            audio_stream = self.client.generate(
                text=text,
                voice=self.voice_id,
                model="eleven_monolingual_v1",
                stream=True
            )
            stream(audio_stream)
        except Exception as e:
            print(f"[TTS Error] {e}")

# Singleton
tts = VoiceSynthesizer()
