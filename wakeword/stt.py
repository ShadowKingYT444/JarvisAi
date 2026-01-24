import speech_recognition as sr
from faster_whisper import WhisperModel
import os
import io
import tempfile

class SpeechToText:
    def __init__(self):
        print("  -> Loading Faster Whisper model (base.en)...")
        # Use 'auto' to use GPU if available, else CPU. 
        # int8 quantization is fast on CPU.
        try:
            self.model = WhisperModel("base.en", device="auto", compute_type="int8")
        except Exception as e:
            print(f"Warning: Failed to load 'auto' device, falling back to CPU. Error: {e}")
            self.model = WhisperModel("base.en", device="cpu", compute_type="int8")
            
        self.recognizer = sr.Recognizer()
        
        # Optimize for speed - snappier response
        self.recognizer.pause_threshold = 0.6  # Stop recording after 0.6s of silence
        self.recognizer.non_speaking_duration = 0.3
        self.recognizer.energy_threshold = 300 # Default is 300, can adjust if noisy
        self.recognizer.dynamic_energy_threshold = True 
        
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("  -> STT Model Loaded.")

    def listen_and_transcribe(self):
        try:
            with sr.Microphone() as source:
                print("  -> Listening...")
                # phrase_time_limit prevents it from getting stuck listening forever
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
            
            print("  -> Transcribing...")
            # faster-whisper works best with file paths or binary streams
            audio_data = io.BytesIO(audio.get_wav_data())
            
            segments, info = self.model.transcribe(audio_data, beam_size=5)
            
            text = "".join([segment.text for segment in segments]).strip()
            
            if not text:
                return None

            return {
                "text": text,
                "language": info.language
            }

        except sr.WaitTimeoutError:
            print("  -> Timeout: No speech detected.")
            return None
        except Exception as e:
            print(f"  -> Error: {e}")
            return None