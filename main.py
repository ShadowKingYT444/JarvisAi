import sys
import asyncio
import qasync
from PyQt6.QtWidgets import QApplication
from wakeword.listener import WakeWordListener
from wakeword.stt import SpeechToText
from agent_logic import agent_service
from jarvis_ui import JarvisOverlay

async def run_jarvis_loop(overlay, loop):
    """
    Main asynchronous loop processing wake word and commands.
    """
    print("--- JARVIS AGENT INITIALIZING ---")
    
    # Initialize components in executor to avoid blocking startup
    try:
        listener = await loop.run_in_executor(None, WakeWordListener)
        stt = await loop.run_in_executor(None, SpeechToText)
    except Exception as e:
        print(f"Startup Error (Audio Components): {e}")
        return

    # Initialize Agent
    try:
        await agent_service.initialize()
    except Exception as e:
        print(f"Agent Startup Error: {e}")
        if 'listener' in locals():
            listener.cleanup()
        return

    print("System Ready. Say 'Jarvis' to activate.")
    
    try:
        while True:
            # 1. Wait for Wake Word (Blocking call run in thread)
            print("Listening for wake word...")
            
            # This runs the blocking listener.listen() in a separate thread,
            # allowing the GUI to stay responsive (if we had animations running).
            wake_detected = await loop.run_in_executor(None, listener.listen)
            
            if wake_detected:
                print("[+] Wake word detected!")
                
                # 2. ACTIVATE UI (Visual Feedback)
                overlay.wake_up()
                # Allow a brief moment for UI to render if needed, though wake_up calls show()
                await asyncio.sleep(0.1) 
                
                # 3. Listen for Command (Blocking call run in thread)
                # We interpret speech after the wake word
                result = await loop.run_in_executor(None, stt.listen_and_transcribe)
                
                # 4. Handle Command
                if result and result.get('text'):
                    # IMMEDIATE UI HIDE
                    overlay.sleep()
                    
                    command = result['text']
                    print(f"Command: {command}")
                    
                    if "exit" in command.lower() or "quit" in command.lower():
                        print("Shutting down.")
                        break
                    
                    # 5. Execute Agent Action
                    # Visual Agent (agent_logic) handles the loop internally
                    await agent_service.process_request(command)
                else:
                    print("[-] Could not understand command.")
                    overlay.sleep()
                
    except asyncio.CancelledError:
        print("Task cancelled.")
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        print("Cleaning up resources...")
        await agent_service.cleanup()
        if 'listener' in locals():
            listener.cleanup()
        # Close the app
        QApplication.instance().quit()

def main():
    # Create the Qt Application
    app = QApplication(sys.argv)
    
    # Create the QAsync Event Loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Create UI
    overlay = JarvisOverlay()
    
    # Schedule the main logic
    loop.create_task(run_jarvis_loop(overlay, loop))
    
    # Run the loop
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
