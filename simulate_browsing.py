
from playwright.sync_api import sync_playwright
import time
import sys

def run():
    try:
        with sync_playwright() as p:
            print("[Sim] Connecting to CDP...", flush=True)
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
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
