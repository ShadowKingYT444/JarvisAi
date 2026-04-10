# Changelog

## v2.0.0 (2026-04-10)

Complete rewrite from script-based prototype to persistent, always-on AI desktop assistant.

### Architecture
- 7-module design: Activation (double-clap) -> Ears (Whisper STT) -> Brain (Gemini 2.0 Flash) -> Hands (11 tools) -> Voice (TTS) -> Face (GUI) -> Daemon
- Platform support: macOS (primary), Windows, Linux

### GUI Installer Wizard
- 5-page setup wizard: dependency checks, API key validation, preferences, clap calibration, auto-start
- Run via `python install.py` or `jarvis install`

### GUI Settings Panel
- 4-tab settings dialog accessible from system tray
- All 28+ config fields with proper widgets (sliders, dropdowns, masked password fields)

### RAM Optimized for Background Use
- Idle footprint: ~60-80 MB (down from ~150 MB)
- Lazy Gemini SDK loading, Whisper model auto-unload after 2min idle
- `--headless` mode skips GUI for even lower RAM

### Tools (via Gemini function calling)
- `web_search` -- Google CSE / SerpAPI
- `open_browser_tabs` -- open URLs in default browser
- `open_application` -- launch apps with fuzzy alias matching
- `close_browser_tab` -- close tabs by title/URL pattern
- `system_command` -- volume, dark mode, screenshot, lock, DnD
- `clipboard_read` / `clipboard_write`
- `focus_mode` -- AI-powered distraction blocking
- `set_reminder` -- persistent timed reminders
- `get_active_tabs` -- list all browser tabs

### CLI
```
jarvis start [--headless]    Start daemon
jarvis stop                  Stop daemon
jarvis text "query"          Send text command
jarvis install [--no-gui]    GUI or CLI setup wizard
jarvis setup                 Alias for install
jarvis config                Edit configuration
jarvis calibrate             Re-calibrate clap detection
```

### Requirements
- Python 3.11+
- Gemini API key (from ai.google.dev)
- Search API key (Google CSE or SerpAPI)
