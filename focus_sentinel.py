import asyncio
import time
from tab_manager import tab_manager
from focus_manager import focus_manager
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
    def __init__(self, overlay, zombie_overlay, scribe_overlay=None):
        self.overlay = overlay # Main UI overlay
        self.zombie_overlay = zombie_overlay
        self.scribe_overlay = scribe_overlay
        self.running = False
        
        # Tab Switching Logic
        self.last_tab_id = None
        self.switch_timestamps = []
        
        # Scrolling Logic
        self.scroll_start_time = 0
        
        # Ghost Writer Logic
        self.current_url_start_time = 0
        self.current_url = None
        self.processed_urls = set() # Avoid re-summarizing same page session
        self.DWELL_THRESHOLD = 30.0 # Seconds to wait before summarizing
        
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
                print(f"[FocusSentinel] Error: {e}")
                pass
            await asyncio.sleep(1.0)

    async def monitor_step(self):
        # 1. Get Active Tab
        active_tab = await tab_manager.get_active_tab()
        if not active_tab:
            # print("[FocusSentinel] No active tab found.") # Noisy
            return

        current_tab_id = active_tab['id']
        current_url = active_tab['url']
        now = time.time()
        
        print(f"[FocusSentinel] Active: {current_url[:50]}...")

        # --- GHOST WRITER TRACKING ---
        if current_url != self.current_url:
            self.current_url = current_url
            self.current_url_start_time = now
        
        dwell_time = now - self.current_url_start_time
        # print(f"[GhostWriter] Dwell: {dwell_time:.1f}s")

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
                
                # Zombie Logic
                if is_scrolling:
                    duration = now - scroll_start
                    time_since_click = now - last_click
                    
                    if duration > self.MAX_SCROLL_DURATION and time_since_click > self.MAX_SCROLL_DURATION:
                        await self.trigger_zombie_mode("Continuous doomscrolling detected.")
                
                # --- GHOST WRITER TRIGGER ---
                time_since_scroll = now - (stats.get('lastScrollTime', 0) / 1000.0)
                
                # DEBUG Trigger Logic
                if dwell_time > 10: # Log only if dwelling a bit
                   print(f"[GhostWriter] Check: Dwell={dwell_time:.1f}s, Processed={current_url in self.processed_urls}, Scrolling={is_scrolling}, time_since_scroll={time_since_scroll:.1f}s")
                
                if (dwell_time > self.DWELL_THRESHOLD and 
                    current_url not in self.processed_urls and 
                    (is_scrolling or time_since_scroll < 10) and  # Recently active on page
                    self.scribe_overlay):
                    
                    print(f"[GhostWriter] Analyzing: {active_tab['title']}...")
                    self.processed_urls.add(current_url)
                    
                    # Extract Content
                    page_content = await target_page.inner_text('body')
                    
                    # Synthesize
                    note = await asyncio.to_thread(
                        focus_manager.synthesize_page_content,
                        active_tab['title'],
                        current_url,
                        page_content
                    )
                    
                    if note:
                        print(f"[GhostWriter] Note generated: {note}")
                        self.scribe_overlay.add_note(note)
                        self.scribe_overlay.show()
                        
                        # FORCE EXIT FOR DEMO? No, let user confirm.
                    else:
                        print("[GhostWriter] No valuable note found.")

            except Exception as e:
                # Page might be closed or navigating
                # print(f"Monitor error: {e}")
                pass

    async def trigger_zombie_mode(self, reason):
        if self.zombie_mode_active:
            return
            
        print(f"[FocusSentinel] 🧟 ZOMBIE MODE TRIGGERED: {reason}")
        self.zombie_mode_active = True
        
        # 1. Overlay
        if self.zombie_overlay:
            self.zombie_overlay.fade_in()
        
        # 2. Voice Nudge
        tts.speak("You're scrolling fast. Do you need a summary of this page, or should we move on?")
        
        # 3. Wait/Reset logic
        asyncio.create_task(self.recovery_loop())

    async def recovery_loop(self):
        """Wait for user interaction to clear zombie mode."""
        print("[FocusSentinel] Waiting for recovery interaction...")
        await asyncio.sleep(5) # Give chance for impact
        
        start_wait = time.time()
        while time.time() - start_wait < 60: # Max 1 min wait?
            await asyncio.sleep(1)
            # For now, simplistic: Fade out after 10s
            if time.time() - start_wait > 10:
                break
                
        if self.zombie_overlay:
            self.zombie_overlay.fade_out()
        self.zombie_mode_active = False
        print("[FocusSentinel] Zombie Mode cleared.")

