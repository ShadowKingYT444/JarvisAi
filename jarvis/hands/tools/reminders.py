"""Reminders tool — schedule and persist timed reminders.

Reminders are stored in ``~/.jarvis/reminders.json`` and restored on init.
When a reminder fires, it emits a ``"reminder_triggered"`` event on the EventBus.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jarvis.hands.platform import Platform
from jarvis.shared.config import JarvisConfig
from jarvis.shared.events import EventBus
from jarvis.shared.types import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class Reminder:
    """A single scheduled reminder."""

    id: str
    message: str
    trigger_at: float  # Unix timestamp
    created_at: float = field(default_factory=time.time)
    fired: bool = False


class ReminderStore:
    """Manages active reminders, persistence, and async scheduling."""

    def __init__(self, config: JarvisConfig, event_bus: EventBus | None = None) -> None:
        self._config = config
        self._event_bus = event_bus
        self._reminders: dict[str, Reminder] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._counter = 0
        self._load()

    # ---- persistence ----

    def _store_path(self) -> Path:
        return Path(self._config.jarvis_home).expanduser() / "reminders.json"

    def _load(self) -> None:
        """Load persisted reminders and reschedule any that haven't fired."""
        path = self._store_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            now = time.time()
            for item in data:
                r = Reminder(**item)
                if r.fired or r.trigger_at <= now:
                    continue  # skip past reminders
                self._reminders[r.id] = r
                self._counter = max(self._counter, int(r.id.split("_")[-1]) + 1)
            logger.info("Loaded %d pending reminder(s) from disk", len(self._reminders))
        except Exception as exc:
            logger.warning("Failed to load reminders: %s", exc)

    def _save(self) -> None:
        """Persist all reminders to disk."""
        path = self._store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(r) for r in self._reminders.values()]
        path.write_text(json.dumps(data, indent=2))

    # ---- scheduling ----

    def schedule_existing(self) -> None:
        """Schedule asyncio tasks for all loaded (unfired) reminders.

        Call this once the event loop is running.
        """
        for r in list(self._reminders.values()):
            if not r.fired and r.id not in self._tasks:
                self._tasks[r.id] = asyncio.ensure_future(self._wait_and_fire(r))

    async def _wait_and_fire(self, reminder: Reminder) -> None:
        """Sleep until trigger time, then fire the reminder."""
        delay = max(0.0, reminder.trigger_at - time.time())
        await asyncio.sleep(delay)

        reminder.fired = True
        self._save()

        logger.info("Reminder fired: %s", reminder.message)
        if self._event_bus:
            await self._event_bus.emit_async("reminder_triggered", {
                "id": reminder.id,
                "message": reminder.message,
            })

        # Cleanup
        self._tasks.pop(reminder.id, None)

    # ---- public API ----

    def add(self, message: str, minutes: float) -> Reminder:
        """Create and schedule a new reminder."""
        self._counter += 1
        rid = f"rem_{self._counter}"
        r = Reminder(
            id=rid,
            message=message,
            trigger_at=time.time() + minutes * 60,
        )
        self._reminders[rid] = r
        self._save()

        # Schedule if event loop is running
        try:
            loop = asyncio.get_running_loop()
            self._tasks[rid] = loop.create_task(self._wait_and_fire(r))
        except RuntimeError:
            # No running loop — caller should call schedule_existing() later
            pass

        return r

    def cancel(self, reminder_id: str) -> bool:
        """Cancel a pending reminder by ID."""
        r = self._reminders.get(reminder_id)
        if r is None or r.fired:
            return False
        r.fired = True  # mark as done
        task = self._tasks.pop(reminder_id, None)
        if task and not task.done():
            task.cancel()
        self._save()
        return True

    def list_pending(self) -> list[Reminder]:
        """Return all unfired reminders sorted by trigger time."""
        return sorted(
            [r for r in self._reminders.values() if not r.fired],
            key=lambda r: r.trigger_at,
        )

    @property
    def count(self) -> int:
        return len([r for r in self._reminders.values() if not r.fired])


# Module-level store (initialised during register())
_store: ReminderStore | None = None


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def set_reminder(message: str, minutes: float) -> ToolResult:
    """Schedule a reminder.

    Args:
        message: The reminder text to speak/display when it fires.
        minutes: Number of minutes from now.

    Returns:
        ToolResult with the reminder ID and trigger time.
    """
    if _store is None:
        return ToolResult(success=False, error="Reminder store not initialised")

    if minutes <= 0:
        return ToolResult(
            success=False,
            error="Minutes must be positive",
            display_text="Cannot set a reminder in the past.",
        )

    r = _store.add(message, minutes)
    return ToolResult(
        success=True,
        data={"id": r.id, "message": r.message, "trigger_at": r.trigger_at, "minutes": minutes},
        display_text=f"Reminder set: '{message}' in {minutes:.0f} minute(s). (ID: {r.id})",
    )


async def cancel_reminder(reminder_id: str) -> ToolResult:
    """Cancel a pending reminder by its ID.

    Args:
        reminder_id: The reminder ID to cancel.
    """
    if _store is None:
        return ToolResult(success=False, error="Reminder store not initialised")

    ok = _store.cancel(reminder_id)
    if ok:
        return ToolResult(
            success=True,
            data={"id": reminder_id},
            display_text=f"Cancelled reminder {reminder_id}.",
        )
    return ToolResult(
        success=False,
        error=f"Reminder '{reminder_id}' not found or already fired",
        display_text=f"Could not cancel '{reminder_id}'.",
    )


async def list_reminders() -> ToolResult:
    """List all pending reminders."""
    if _store is None:
        return ToolResult(success=False, error="Reminder store not initialised")

    pending = _store.list_pending()
    if not pending:
        return ToolResult(
            success=True,
            data=[],
            display_text="No pending reminders.",
        )

    now = time.time()
    lines = [f"{len(pending)} pending reminder(s):"]
    for r in pending:
        remaining = max(0, r.trigger_at - now)
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        lines.append(f"  [{r.id}] '{r.message}' — in {mins}m {secs}s")

    return ToolResult(
        success=True,
        data=[asdict(r) for r in pending],
        display_text="\n".join(lines),
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(executor: Any, platform: Platform, config: JarvisConfig) -> None:
    """Register reminder tools with the executor."""
    global _store
    _store = ReminderStore(config)
    _store.schedule_existing()

    executor.register("set_reminder", set_reminder)
    executor.register("cancel_reminder", cancel_reminder)
    executor.register("list_reminders", list_reminders)
