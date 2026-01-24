from pvrecorder import PvRecorder
import sys

# We use the same index (0) you found earlier
recorder = PvRecorder(device_index=0, frame_length=512)
recorder.start()

print("--- MIC TEST: SPEAK NOW (Ctrl+C to stop) ---")

try:
    while True:
        pcm = recorder.read()
        
        # Calculate how loud the frame is
        volume = sum(abs(x) for x in pcm) / len(pcm)
        
        # Draw a bar based on volume
        num_bars = int(volume / 100)  # Adjust divisor if too sensitive/insensitive
        bar_visual = "|" * num_bars
        
        # Print continuously on one line
        sys.stdout.write(f"\rVolume: {bar_visual:<50}")
        sys.stdout.flush()

except KeyboardInterrupt:
    print("\nStopping...")
    recorder.stop()
    recorder.delete()