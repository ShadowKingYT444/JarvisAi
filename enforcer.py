"""
Deep Work Fortress - The Enforcer
Connects FocusManager to real Chrome/Safari browser and takes action on distracting tabs.

Uses AppleScript on macOS - no debug mode required, works on managed Macs.

Features:
- Scans real browser tabs via AppleScript
- Evaluates tabs with FocusManager (Gemini AI)
- Safely closes distractions (backs up to JSON first)
- Can restore closed tabs from backup
"""

import os
import json
from datetime import datetime

from focus_manager import FocusManager
from browser_control import AppleScriptBrowserControl


class Enforcer:
    """
    The Enforcer connects to Chrome/Safari, evaluates tabs, and closes distractions.
    Uses AppleScript instead of CDP - works on managed Macs.
    """
    
    BACKUP_FILE = "session_backup.json"
    
    def __init__(self, browser: str = "chrome"):
        """
        Args:
            browser: "chrome" or "safari"
        """
        self.browser_control = AppleScriptBrowserControl(browser)
        self.focus_manager = FocusManager()
        self.browser_name = browser
    
    def _load_backup(self) -> list[dict]:
        """Load existing backup file."""
        if os.path.exists(self.BACKUP_FILE):
            try:
                with open(self.BACKUP_FILE, "r") as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_backup(self, tabs: list[dict]):
        """Save tabs to backup file."""
        # Load existing backup and append
        existing = self._load_backup()
        
        # Add timestamp to new entries
        timestamp = datetime.now().isoformat()
        for tab in tabs:
            tab["closed_at"] = timestamp
        
        # Append new tabs
        existing.extend(tabs)
        
        with open(self.BACKUP_FILE, "w") as f:
            json.dump(existing, f, indent=2)
    
    def scan_tabs(self) -> list[dict]:
        """
        Scan all open tabs.
        
        Returns:
            List of tab dicts with {id, title, url, window_id, tab_index}
        """
        tabs = self.browser_control.get_tabs()
        print(f"[Enforcer] Found {len(tabs)} tabs in {self.browser_name.title()}")
        return tabs
    
    def enforce_focus(self, goal: str, dry_run: bool = False) -> dict:
        """
        Main enforcement function. Evaluates tabs and closes distractions.
        
        Args:
            goal: The user's current work goal
            dry_run: If True, only report what would be closed without actually closing
            
        Returns:
            Summary dict with counts and details
        """
        print(f"\n🏰 DEEP WORK FORTRESS - Enforcing Focus")
        print(f"🎯 Goal: {goal}")
        print(f"🌐 Browser: {self.browser_name.title()}")
        print("=" * 60)
        
        # 1. Scan real tabs
        tabs = self.scan_tabs()
        if not tabs:
            print("\n❌ No tabs found or browser is not running")
            return {"error": "No tabs found or browser not running"}
        
        # 2. Prepare tabs for evaluation
        tabs_for_eval = [
            {"id": t["id"], "title": t["title"], "url": t["url"]}
            for t in tabs
        ]
        
        # 3. Evaluate with FocusManager
        print("\n📊 Evaluating tabs with AI...")
        result = self.focus_manager.evaluate_tabs(tabs_for_eval, goal)
        
        # Print evaluation
        self.focus_manager.print_evaluation(result)
        
        # 4. Identify tabs to close
        tabs_to_close = [t for t in tabs if t["id"] in result["tabs_to_hide"]]
        
        if not tabs_to_close:
            print("\n✨ All tabs are relevant! No distractions found.")
            return {
                "closed": 0,
                "kept": len(tabs),
                "tabs_closed": [],
                "backup_file": None
            }
        
        # 5. Backup before closing
        backup_data = [
            {"title": t["title"], "url": t["url"]}
            for t in tabs_to_close
        ]
        
        if dry_run:
            print(f"\n🔍 DRY RUN: Would close {len(tabs_to_close)} tabs:")
            for tab in tabs_to_close:
                print(f"   - {tab['title'][:60]}")
            return {
                "closed": 0,
                "would_close": len(tabs_to_close),
                "kept": len(result["tabs_to_keep"]),
                "tabs_to_close": [t["title"] for t in tabs_to_close],
                "dry_run": True
            }
        
        # Save backup
        self._save_backup(backup_data)
        print(f"\n💾 Backed up {len(tabs_to_close)} tabs to {self.BACKUP_FILE}")
        
        # 6. Close distraction tabs
        # Sort by tab_index descending to avoid index shifting issues
        tabs_to_close_sorted = sorted(
            tabs_to_close, 
            key=lambda t: (t["window_id"], t["tab_index"]), 
            reverse=True
        )
        
        closed_count = 0
        closed_titles = []
        
        for tab in tabs_to_close_sorted:
            try:
                title = tab["title"]
                success = self.browser_control.close_tab(tab["window_id"], tab["tab_index"])
                if success:
                    closed_count += 1
                    closed_titles.append(title)
                    print(f"   🚫 Closed: {title[:50]}")
                else:
                    print(f"   ⚠️ Could not close: {title[:50]}")
            except Exception as e:
                print(f"   ⚠️ Error closing '{tab['title'][:30]}': {e}")
        
        # 7. Summary
        print("\n" + "=" * 60)
        print(f"✅ Closed {closed_count} distracting tabs")
        print(f"📌 Kept {len(result['tabs_to_keep'])} relevant tabs")
        print(f"💾 Backup saved to: {self.BACKUP_FILE}")
        print("=" * 60)
        
        return {
            "closed": closed_count,
            "kept": len(result["tabs_to_keep"]),
            "tabs_closed": closed_titles,
            "backup_file": self.BACKUP_FILE
        }
    
    def restore_session(self, limit: int = None) -> dict:
        """
        Restore previously closed tabs from backup.
        
        Args:
            limit: Maximum number of tabs to restore (None = all)
            
        Returns:
            Summary dict with restore counts
        """
        backup = self._load_backup()
        if not backup:
            print("[Enforcer] No backup found to restore")
            return {"restored": 0, "error": "No backup found"}
        
        # Get tabs to restore
        tabs_to_restore = backup[-limit:] if limit else backup
        
        print(f"\n🔄 Restoring {len(tabs_to_restore)} tabs from backup...")
        
        restored_count = 0
        
        for tab in tabs_to_restore:
            try:
                success = self.browser_control.open_url(tab["url"], new_tab=True)
                if success:
                    restored_count += 1
                    print(f"   ✅ Restored: {tab['title'][:50]}")
                else:
                    print(f"   ⚠️ Could not restore: {tab['title'][:50]}")
            except Exception as e:
                print(f"   ⚠️ Error restoring: {e}")
        
        # Clear restored tabs from backup
        if restored_count > 0:
            remaining = backup[:-len(tabs_to_restore)] if limit else []
            with open(self.BACKUP_FILE, "w") as f:
                json.dump(remaining, f, indent=2)
        
        print(f"\n✅ Restored {restored_count} tabs")
        return {"restored": restored_count}
    
    def show_backup(self):
        """Display the current backup contents."""
        backup = self._load_backup()
        
        if not backup:
            print("\n📭 Backup is empty - no closed tabs saved")
            return
        
        print(f"\n💾 Backup contains {len(backup)} tabs:")
        print("-" * 60)
        for i, tab in enumerate(backup):
            closed_at = tab.get("closed_at", "Unknown time")
            print(f"  [{i}] {tab['title'][:50]}")
            print(f"      URL: {tab['url'][:50]}")
            print(f"      Closed: {closed_at}")
        print("-" * 60)


# --- CLI Interface ---
def main():
    """Command-line interface for the Enforcer."""
    import sys
    
    # Default to Chrome
    browser = "chrome"
    
    # Check for browser flag
    if "--safari" in sys.argv:
        browser = "safari"
        sys.argv.remove("--safari")
    elif "--chrome" in sys.argv:
        browser = "chrome"
        sys.argv.remove("--chrome")
    
    e = Enforcer(browser=browser)
    
    if len(sys.argv) < 2:
        print("""
🏰 DEEP WORK FORTRESS - Enforcer (AppleScript Edition)

Usage:
  python enforcer.py focus "Your work goal here"     # Evaluate and close distractions
  python enforcer.py focus "Your goal" --dry-run    # Preview without closing
  python enforcer.py restore                         # Restore closed tabs from backup
  python enforcer.py backup                          # Show backup contents
  python enforcer.py scan                            # Just scan and list tabs

Options:
  --chrome    Use Chrome (default)
  --safari    Use Safari instead

Examples:
  python enforcer.py focus "Learning React Hooks"
  python enforcer.py focus "Writing documentation" --dry-run
  python enforcer.py scan --safari
  python enforcer.py restore
""")
        return
    
    command = sys.argv[1]
    
    if command == "focus":
        if len(sys.argv) < 3:
            print("Error: Please provide a goal. Example: python enforcer.py focus \"Learning Python\"")
            return
        
        goal = sys.argv[2]
        dry_run = "--dry-run" in sys.argv
        
        e.enforce_focus(goal, dry_run=dry_run)
        
    elif command == "restore":
        e.restore_session()
        
    elif command == "backup":
        e.show_backup()
        
    elif command == "scan":
        tabs = e.scan_tabs()
        print("\n📑 Open tabs:")
        for tab in tabs:
            print(f"  [{tab['id']}] {tab['title'][:50]}")
            print(f"      {tab['url'][:60]}")
        
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
