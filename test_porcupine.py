import os
import pvporcupine
from dotenv import load_dotenv
import sys

# Load env variables
load_dotenv()

access_key = os.getenv("PICOVOICE_ACCESS_KEY")
print(f"Access Key found: {bool(access_key)}")
# print(f"Key length: {len(access_key) if access_key else 0}")

if not access_key:
    print("ERROR: No access key provided.")
    sys.exit(1)

try:
    print("Attempting to initialize Porcupine...")
    porcupine = pvporcupine.create(
        access_key=access_key,
        keywords=['jarvis']
    )
    print("SUCCESS: Porcupine initialized.")
    porcupine.delete()
except Exception as e:
    print("FAILURE: Porcupine failed to initialize.")
    print(e)
