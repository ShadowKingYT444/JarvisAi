import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyQt6.QtWidgets import QApplication
from zombie_overlay import ZombieOverlay
from focus_sentinel import FocusSentinel
import tab_manager as tm_module
from wakeword import tts as tts_module

async def run_verification():
    with open("verification_result.log", "w", encoding="utf-8") as log_file:
        def log(msg):
            print(msg)
            log_file.write(str(msg) + "\n")

        log("STARTING ZOMBIE MODE VERIFICATION")
        log("=" * 60)

        # 1. Setup Mocks
        log("[1/4] Setting up Mocks...")
        
        # Mock TTS
        tts_module.tts = MagicMock()
        tts_module.tts.speak = MagicMock(side_effect=lambda x: log(f"   [MOCK AUDIO] '{x}'"))
        
        # Mock TabManager
        mock_page = AsyncMock()
        mock_page.url = "https://github.com/test"
        mock_page.evaluate = AsyncMock()  # For JS injection result
        
        tm_module.tab_manager.get_active_tab = AsyncMock()
        tm_module.tab_manager.context = MagicMock()
        tm_module.tab_manager.context.pages = [mock_page]
        
        
        # 2. Setup Overlay
        log("[2/4] Initializing Overlay...")
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            overlay = ZombieOverlay()
            # overlay.show() # Don't show immediately, let logic trigger it
            log("   Overlay initialized")
        except Exception as e:
            log(f"   Overlay init failed: {e}")
            return

        # 3. Test Rapid Tab Switching
        log("\n[3/4] Testing Rapid Tab Switching Logic...")
        sentinel = FocusSentinel(overlay)
        
        # Simulate switching 5 times quickly
        log("   -> Simulating 5 quick tab switches...")
        
        for i in range(5):
            # Return different ID each time
            tm_module.tab_manager.get_active_tab.return_value = {'id': i, 'url': f'url{i}'}
            await sentinel.monitor_step()
            await asyncio.sleep(0.1)
            
        log("   -> Checking if Zombie Mode triggered...")
        if sentinel.zombie_mode_active:
            log("   SUCCESS: Zombie Mode triggered by tab switching!")
            log("   -> Resetting for next test...")
            sentinel.zombie_mode_active = False # Manual reset
            overlay.hide()
        else:
            log("   FAILURE: Zombie Mode DID NOT trigger.")

        # 4. Test Doomscrolling
        log("\n[4/4] Testing Doomscrolling Logic...")
        
        # Setup "Active" tab
        tm_module.tab_manager.get_active_tab.return_value = {'id': 99, 'url': 'https://github.com/test'}
        
        # Start monitoring. Logic requires: duration > MAX_SCROLL (120s) AND time_since_click > MAX_SCROLL
        # We will lower the threshold in the instance for testing
        sentinel.MAX_SCROLL_DURATION = 0.5 # 0.5 seconds for test
        
        # Prepare Mock JS Return
        # Return: isScrolling=True, scrollStartTime=old, lastClickTime=old
        import time
        now = time.time() * 1000 # JS uses millis
        start_time = now - 2000 # 2 seconds ago
        
        mock_page.evaluate.return_value = {
            'isScrolling': True,
            'scrollStartTime': start_time,
            'lastClickTime': start_time 
        }
        
        log("   -> Simulating continuous scroll > threshold...")
        await sentinel.monitor_step()
        
        if sentinel.zombie_mode_active:
            log("   SUCCESS: Zombie Mode triggered by scrolling!")
        else:
            log("   FAILURE: Zombie Mode logic failed for scrolling.")
            
        log("=" * 60)
        log("VERIFICATION COMPLETE")
        
        # Cleanup
        overlay.close()

if __name__ == "__main__":
    asyncio.run(run_verification())
