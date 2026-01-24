import speech_recognition as sr
from elevenlabs.client import ElevenLabs
import os
import io

class SpeechToText:
    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("Missing ELEVENLABS_API_KEY in .env")
            
        self.client = ElevenLabs(api_key=self.api_key)
        self.recognizer = sr.Recognizer()
        
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

    def listen_and_transcribe(self):
        try:
            with sr.Microphone() as source:
                print("  -> Listening for command...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=15)
            
            print("  -> Sending to ElevenLabs...")
            audio_data = io.BytesIO(audio.get_wav_data())
            audio_data.name = "audio.wav" 

            transcription = self.client.speech_to_text.convert(
                file=audio_data,
                model_id="scribe_v1", 
                tag_audio_events=False
            )
            
            return {
                "text": transcription.text,
                "language": transcription.language_code
            }

        except sr.WaitTimeoutError:
            print("  -> Timeout: No speech detected.")
            return None
        except Exception as e:
            print(f"  -> Error: {e}")
            return None