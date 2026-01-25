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
            # KEYWORDS: Index 0 = Jarvis, Index 1 = Alexa (Alyssa/Soren Proxy)
            self.porcupine = pvporcupine.create(
                access_key=self.access_key,
                keywords=['jarvis', 'alexa']
            )
        except Exception as e:
            raise ValueError(f"Porcupine failed to initialize. Original Error: {e}")

        # 2. Initialize Recorder (The Ears)
        self.recorder = PvRecorder(
            device_index=-1, 
            frame_length=self.porcupine.frame_length
        )

    def listen(self):
        if self.recorder is None:
            self.recorder = PvRecorder(
                device_index=-1, 
                frame_length=self.porcupine.frame_length
            )
            
        print("Waiting for wake word ('Jarvis' or 'Alexa')...")
        self.recorder.start()
        
        try:
            while True:
                pcm = self.recorder.read()
                keyword_index = self.porcupine.process(pcm)
                
                if keyword_index >= 0:
                    self.recorder.stop()
                    # Release resources so STT can use the mic
                    # Note: We don't delete self.recorder entirely if we want to reuse it, 
                    # but PyAudio/PvRecorder might hold the device handle.
                    # Re-instantiating might be safer for conflicts, or just stopping is enough?
                    # The issue 2 says "explicit recorder.delete()".
                    # If we delete, we must re-create in __init__ or logic?
                    # Actually, just stopping might not be enough on Windows/Mac. 
                    # Let's try to delete and re-create if needed, or just delete here 
                    # and let the caller manage re-init?
                    # The caller (VoiceWorker) loops `listen()`.
                    # If we delete here, the NEXT call to `self.recorder.read()` will fail.
                    # So we need to RE-init the recorder next time `listen()` is called.
                    self.recorder.delete() 
                    self.recorder = None
                    # Return the index (0 or 1) so main.py knows WHICH persona was triggered
                    return keyword_index
        except Exception as e:
            print(f"Error while listening: {e}")
            if self.recorder:
                self.recorder.stop()
            return -1

    def cleanup(self):
        if self.recorder:
            self.recorder.delete()
        if self.porcupine:
            self.porcupine.delete()