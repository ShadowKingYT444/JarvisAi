import os
import pvporcupine
from dotenv import load_dotenv

load_dotenv()
access_key = os.getenv("PICOVOICE_ACCESS_KEY")

try:
    print("Testing default keyword 'porcupine'...")
    porcupine = pvporcupine.create(
        access_key=access_key,
        keywords=['porcupine']
    )
    print("SUCCESS: Default keyword 'porcupine' loaded.")
    porcupine.delete()
except Exception as e:
    print(f"FAILURE with 'porcupine': {e}")
