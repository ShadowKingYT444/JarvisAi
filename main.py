import sys
import asyncio
from wakeword.listener import WakeWordListener
from wakeword.stt import SpeechToText
from agent import BrowserAgent

async def main():
    print("--- JARVIS AGENT INITIALIZING ---")

    try:
        listener = WakeWordListener()
        stt = SpeechToText()
    except Exception as e:
        print(f"Startup Error: {e}")
        return

    # Initialize the browser agent
    agent = BrowserAgent()
    try:
        await agent.start()
    except Exception as e:
        print(f"Agent Startup Error: {e}")
        listener.cleanup()
        return

    print("System Ready. Say 'Jarvis' to activate.")
    
    try:
        while True:
            # 1. Block locally until "Jarvis" is heard
            listener.listen()
            print("[+] Wake word detected!")
            
            # 2. Record and Transcribe via Cloud
            result = stt.listen_and_transcribe()
            
            # 3. Handle Output
            if result and result['text']:
                command = result['text']
                language = result.get('language', 'en')
                print(f"Command ({language}): {command}")
                
                if "exit" in command.lower() or "quit" in command.lower():
                    print("Shutting down.")
                    break
                
                # 4. Send the transcribed text to the agent
                await agent.run_loop(command)
            else:
                print("[-] Could not understand.")
                
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        await agent.stop()
        listener.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
