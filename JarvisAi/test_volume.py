from pvrecorder import PvRecorder
import sys

# Connect to Mic Index 0
recorder = PvRecorder(device_index=0, frame_length=512)
recorder.start()

print("--- SPEAK NOW (Press Ctrl+C to stop) ---")

try:
    while True:
        pcm = recorder.read()
        # Calculate volume
        volume = sum(abs(x) for x in pcm) / len(pcm)
        
        # Visual Bar
        bars = int(volume / 50) 
        print(f"\rVolume: {'|' * bars}".ljust(50), end="")
        
except KeyboardInterrupt:
    print("\nStopping...")
    recorder.stop()
    recorder.delete()
