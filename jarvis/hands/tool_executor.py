"""Registry-based tool executor for Jarvis.

Auto-discovers and registers all built-in tools from the tools/ package,
then dispatches ToolCall requests to the appropriate handler.
"""

import importlib
import logging
import pkgutil
import time
from typing import Any, Callable, Coroutine

from jarvis.hands.platform import Platform
from jarvis.shared.config import JarvisConfig
from jarvis.shared.types import ToolResult

logger = logging.getLogger(__name__)

# Type alias for tool handlers
ToolHandler = Callable[..., Coroutine[Any, Any, ToolResult]]


class ToolExecutor:
    """Central dispatcher that maps tool names to async handler functions."""

    def __init__(self, platform: Platform, config: JarvisConfig) -> None:
        self.platform = platform
        self.config = config
        self._handlers: dict[str, ToolHandler] = {}
        self._auto_register()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, name: str, handler: ToolHandler) -> None:
        """Register a named tool handler.

        Args:
            name: Unique tool name (e.g. ``"web_search"``).
            handler: Async callable that accepts keyword arguments
                     and returns a :class:`ToolResult`.
        """
        if name in self._handlers:
            logger.warning("Overwriting existing handler for tool '%s'", name)
        self._handlers[name] = handler
        logger.debug("Registered tool: %s", name)

    @property
    def registered_tools(self) -> list[str]:
        """Return a sorted list of all registered tool names."""
        return sorted(self._handlers)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(self, tool_name: str, args: dict[str, Any] | None = None) -> ToolResult:
        """Look up *tool_name* and invoke its handler with *args*.

        Returns a :class:`ToolResult` even on failure (``success=False``).
        """
        handler = self._handlers.get(tool_name)
        if handler is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
                display_text=f"No handler registered for '{tool_name}'.",
            )

        args = args or {}
        start = time.monotonic()
        try:
            result = await handler(**args)
            elapsed = time.monotonic() - start
            logger.info("Tool '%s' completed in %.2fs (ok=%s)", tool_name, elapsed, result.success)
            return result
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.exception("Tool '%s' raised after %.2fs", tool_name, elapsed)
            return ToolResult(
                success=False,
                error=str(exc),
                display_text=f"Tool '{tool_name}' failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Auto-discovery
    # ------------------------------------------------------------------

    def _auto_register(self) -> None:
        """Import every module inside ``jarvis.hands.tools`` and call its
        ``register(executor, platform, config)`` function if present.
        """
        package_name = "jarvis.hands.tools"
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            logger.warning("Could not import %s — no tools will be registered", package_name)
            return

        for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
            fqn = f"{package_name}.{modname}"
            try:
                mod = importlib.import_module(fqn)
            except Exception:
                logger.exception("Failed to import tool module %s", fqn)
                continue

            register_fn = getattr(mod, "register", None)
            if callable(register_fn):
                try:
                    register_fn(self, self.platform, self.config)
                    logger.debug("Auto-registered tools from %s", fqn)
                except Exception:
                    logger.exception("register() failed in %s", fqn)
