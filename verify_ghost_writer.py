import subprocess
import time
import os
import sys
import threading

def log(msg):
    print(msg, flush=True)
    with open("verification_result.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def stream_reader(pipe, name, stop_event):
    """Reads from a pipe and prints line by line."""
    try:
        for line in iter(pipe.readline, ''):
            if stop_event.is_set():
                break
            msg = f"[{name}] {line.strip()}"
            print(msg, flush=True)
            with open("verification_result.log", "a", encoding="utf-8") as f:
                f.write(msg + "\n")
                
            if "[GhostWriter] Note generated:" in line:
                log(f"\n✅ SUCCESS: Ghost Writer triggered! Found note: {line.strip()}\n")
    except Exception:
        pass

def main():
    # Clear log
    with open("verification_result.log", "w") as f:
        f.write("Starting...\n")

    log("🚀 Starting Ghost Writer Verification...")

    log("Cleaning up processes...")
    subprocess.run("taskkill /F /IM chrome.exe", shell=True, stderr=subprocess.DEVNULL)
    time.sleep(2)

    log("Launching Chrome...")
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(chrome_path):
        chrome_path = "chrome"
    
    chrome_cmd = [
        chrome_path,
        "--remote-debugging-port=9222",
        "--user-data-dir=C:\\Temp\\ChromeProfile",
        "--no-first-run",
        "about:blank"
    ]
    
    try:
        # Capture stderr to see if Chrome complains
        chrome_proc = subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        t_chrome_err = threading.Thread(target=stream_reader, args=(chrome_proc.stderr, "CHROME", stop_event))
        t_chrome_err.start()
        log("Chrome launched.")
    except Exception as e:
        log(f"Failed to launch Chrome: {e}")
        return

    time.sleep(8) # Increased wait time

    log("Starting Jarvis Agent...")
    env = os.environ.copy()
    # Use -u for unbuffered output
    jarvis_proc = subprocess.Popen(
        [sys.executable, "-u", "main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env
    )
    
    # ... (threads start)

    time.sleep(8) # Increased wait time for Jarvis

    log("Simulating User Browsing via Playwright...")
    sim_script = """
from playwright.sync_api import sync_playwright
import time
import sys

def run():
    try:
        with sync_playwright() as p:
            print("[Sim] Connecting to CDP...", flush=True)
            # Use 127.0.0.1 explicitly
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            if not context.pages:
                page = context.new_page()
            else:
                page = context.pages[0]
                
            print("[Sim] Navigating to documentation...", flush=True)
            # Use a real technical page to ensure Gemini has something to summarize
            page.goto("https://playwright.dev/python/docs/intro") 
            
            print("[Sim] Dwelling for 40 seconds with activity...", flush=True)
            for i in range(40):
                page.mouse.wheel(0, 100) # Scroll down
                time.sleep(0.5)
                page.mouse.wheel(0, -50) # Scroll up
                time.sleep(0.5)
                if i % 5 == 0:
                    print(f"[Sim] Time: {i}s", flush=True)
                    
            print("[Sim] Browsing complete.", flush=True)
            browser.close()
    except Exception as e:
        print(f"[Sim] Error: {e}", flush=True)

if __name__ == "__main__":
    run()
"""
    with open("simulate_browsing.py", "w", encoding="utf-8") as f:
        f.write(sim_script)

    sim_proc = subprocess.Popen(
        [sys.executable, "-u", "simulate_browsing.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    
    t_sim_out = threading.Thread(target=stream_reader, args=(sim_proc.stdout, "USER_SIM", stop_event))
    t_sim_out.start()

    sim_proc.wait()
    time.sleep(5)

    log("Stopping everything...")
    stop_event.set()
    jarvis_proc.terminate()
    
    subprocess.run("taskkill /F /IM chrome.exe", shell=True, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    main()
