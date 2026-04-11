"""Shared dataclasses and enums used across all Jarvis modules."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class JarvisState(Enum):
    IDLE = "idle"
    INITIALIZING = "initializing"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"
    FOCUS_MODE = "focus_mode"


@dataclass
class TabInfo:
    title: str
    url: str
    browser: str
    window_index: int
    tab_index: int


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str
    source: str


@dataclass
class ToolCall:
    name: str
    arguments: dict
    result: "ToolResult | None" = None


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    display_text: str = ""
    error: str | None = None


@dataclass
class BrainResponse:
    spoken_text: str
    tools_invoked: list[ToolCall] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class TranscriptResult:
    text: str
    confidence: float
    duration_ms: int
    language: str = "en"
