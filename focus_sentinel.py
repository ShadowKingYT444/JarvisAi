import asyncio
import time
from tab_manager import tab_manager
from wakeword.tts import tts

# JS to inject for tracking
TRACKER_JS = """
if (!window.__jarvis_tracker) {
    window.__jarvis_tracker = {
        lastScrollTime: Date.now(),
        lastClickTime: Date.now(),
        isScrolling: false,
        scrollStartTime: 0
    };
    
    window.addEventListener('scroll', () => {
        const now = Date.now();
        window.__jarvis_tracker.lastScrollTime = now;
        if (!window.__jarvis_tracker.isScrolling) {
            window.__jarvis_tracker.isScrolling = true;
            window.__jarvis_tracker.scrollStartTime = now;
        }
        
        clearTimeout(window.__jarvis_scrollTimeout);
        window.__jarvis_scrollTimeout = setTimeout(() => {
            window.__jarvis_tracker.isScrolling = false;
        }, 200); 
    });
    
    window.addEventListener('click', () => {
        window.__jarvis_tracker.lastClickTime = Date.now();
    });
    
    window.addEventListener('keydown', () => {
        window.__jarvis_tracker.lastClickTime = Date.now();
    });
}
window.__jarvis_tracker;
"""

class FocusSentinel:
    def __init__(self, overlay):
        self.overlay = overlay
        self.running = False
        
        # Tab Switching Logic
        self.last_tab_id = None
        self.switch_timestamps = []
        
        # Scrolling Logic
        self.scroll_start_time = 0
        
        # Config
        self.MAX_SWITCHES = 4      # Switched 4 times...
        self.SWITCH_WINDOW = 10.0  # ...in 10 seconds
        self.MAX_SCROLL_DURATION = 120 # 2 minutes continuous scrolling
        
        self.zombie_mode_active = False

    async def start(self):
        """Start the monitoring loop."""
        self.running = True
        print("[FocusSentinel] Monitoring started...")
        while self.running:
            try:
                await self.monitor_step()
            except Exception as e:
                # print(f"[FocusSentinel] Error: {e}")
                pass
            await asyncio.sleep(1.0)

    async def monitor_step(self):
        # 1. Get Active Tab
        active_tab = await tab_manager.get_active_tab()
        if not active_tab:
            return

        current_tab_id = active_tab['id']
        now = time.time()

        # 2. Check Tab Switching
        if self.last_tab_id is not None and current_tab_id != self.last_tab_id:
            # Switched!
            self.switch_timestamps.append(now)
            # Clean old timestamps
            self.switch_timestamps = [t for t in self.switch_timestamps if now - t < self.SWITCH_WINDOW]
            
            if len(self.switch_timestamps) >= self.MAX_SWITCHES:
                await self.trigger_zombie_mode("Rapid tab switching detected.")
                self.switch_timestamps = [] # Reset

        self.last_tab_id = current_tab_id

        # 3. Check Scrolling (Inject JS)
        # We need the actual Page object. TabManager wraps it but we can access context.
        context = tab_manager.context
        if not context or not context.pages:
            return

        # Try to find the page object matching the active tab
        # This is tricky because 'get_active_tab' returns dict.
        # We'll assume the first page or iterate.
        target_page = None
        for page in context.pages:
            if page.url == active_tab['url']:
                target_page = page
                break
        
        if target_page:
            try:
                # Inject/READ stats
                stats = await target_page.evaluate(TRACKER_JS)
                
                # Analyze Stats
                is_scrolling = stats.get('isScrolling', False)
                scroll_start = stats.get('scrollStartTime', 0) / 1000.0 # to seconds
                last_click = stats.get('lastClickTime', 0) / 1000.0
                
                if is_scrolling:
                    duration = now - scroll_start
                    # Also check if no click happened recently
                    time_since_click = now - last_click
                    
                    if duration > self.MAX_SCROLL_DURATION and time_since_click > self.MAX_SCROLL_DURATION:
                        await self.trigger_zombie_mode("Continuous doomscrolling detected.")
                
            except Exception as e:
                # Page might be closed or navigating
                pass

    async def trigger_zombie_mode(self, reason):
        if self.zombie_mode_active:
            return
            
        print(f"[FocusSentinel] 🧟 ZOMBIE MODE TRIGGERED: {reason}")
        self.zombie_mode_active = True
        
        # 1. Overlay
        self.overlay.fade_in()
        
        # 2. Voice Nudge
        tts.speak("You're scrolling fast. Do you need a summary of this page, or should we move on?")
        
        # 3. Wait/Reset logic
        # For now, we just auto-reset after some time or let user dismiss?
        # The user visual overlay should probably stay until user does something.
        
        # Let's auto-reset the flag after 30s so we don't spam, 
        # but the overlay might need manual dismissal or fade out?
        # User said "The screen slowly desaturates... to signal loss of focus"
        # It doesn't say how to UN-signal. 
        # I'll assume if user interacts (clicks), we should clear it.
        
        # Start a recovery checks loop
        asyncio.create_task(self.recovery_loop())

    async def recovery_loop(self):
        """Wait for user interaction to clear zombie mode."""
        print("[FocusSentinel] Waiting for recovery interaction...")
        await asyncio.sleep(5) # Give chance for impact
        
        start_wait = time.time()
        while time.time() - start_wait < 60: # Max 1 min wait?
            # Check for generic activity?
            # Or just fade out after audio finishes?
            await asyncio.sleep(1)
            
            # For now, simplistic: Fade out after 10s
            if time.time() - start_wait > 10:
                break
                
        self.overlay.fade_out()
        self.zombie_mode_active = False
        print("[FocusSentinel] Zombie Mode cleared.")

