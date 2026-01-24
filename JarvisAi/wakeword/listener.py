import pvporcupine
from pvrecorder import PvRecorder
import os
from dotenv import load_dotenv

load_dotenv()

class WakeWordListener:
    def __init__(self):
        self.access_key = os.getenv("PICOVOICE_ACCESS_KEY")
        if not self.access_key:
            raise ValueError("Missing PICOVOICE_ACCESS_KEY in .env")

        try:
            # 1. Initialize Porcupine (The Brain)
            # REMOVED: sensitivities=[0.7] (Back to default 0.5)
            self.porcupine = pvporcupine.create(
                access_key=self.access_key,
                keywords=['jarvis']
            )
        except Exception as e:
            raise ValueError(f"Porcupine failed to initialize. Please check your PICOVOICE_ACCESS_KEY in .env. It may be invalid, expired, or you may have reached your usage limit. Original Error: {e}")

        # 2. Initialize Recorder (The Ears)
        # CHANGED: device_index=-1 (Auto-detects the best mic on ANY computer)
        self.recorder = PvRecorder(
            device_index=-1, 
            frame_length=self.porcupine.frame_length
        )

    def listen(self):
        print("Waiting for wake word ('Jarvis')...")
        self.recorder.start()
        
        try:
            while True:
                pcm = self.recorder.read()
                keyword_index = self.porcupine.process(pcm)
                
                if keyword_index >= 0:
                    self.recorder.stop()
                    return True
        except Exception as e:
            print(f"Error while listening: {e}")
            self.recorder.stop()
            return False

    def cleanup(self):
        if self.recorder:
            self.recorder.delete()
        if self.porcupine:
            self.porcupine.delete()