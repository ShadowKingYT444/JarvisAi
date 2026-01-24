from pvrecorder import PvRecorder

print("\n--- AVAILABLE DEVICES ---")
for index, device in enumerate(PvRecorder.get_available_devices()):
    print(f"Index: {index} - {device}")
print("-----------------------\n")