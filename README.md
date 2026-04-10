# Jarvis AI Desktop Assistant v2.0

![Python](https://img.shields.io/badge/python-3.11%2B-yellow.svg)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey.svg)
![Powered By](https://img.shields.io/badge/Powered%20By-Gemini%202.0%20Flash-orange.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

> **Always-on, tool-using AI assistant activated by double-clap detection.**

Jarvis is a persistent desktop AI agent that listens for a double-clap, takes voice commands, executes actions on your computer, and speaks results back. It uses Gemini 2.0 Flash with native function calling to search the web, control your browser, open apps, manage focus sessions, and more.

---

## Architecture

```
JARVIS DAEMON (always-on)

  ACTIVATION ──> EARS ──> BRAIN ──> HANDS (tools)
  (clap detect)  (STT)    (Gemini)   |
                                      ├── web_search
       VOICE <──────────────────────  ├── open_browser_tabs
       (TTS)                          ├── open_application
                                      ├── close_browser_tab
       FACE <───────────────────────  ├── system_command
       (tray + HUD)                   ├── focus_mode
                                      ├── clipboard
                                      └── set_reminder
```

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| LLM | Google Gemini 2.0 Flash (native function calling) |
| STT | Faster-Whisper (local, private) |
| TTS | macOS `say` / ElevenLabs / pyttsx3 |
| Activation | Custom double-clap detector (sounddevice + scipy) |
| GUI | PyQt6 system tray + floating HUD |
| Browser Control | AppleScript (macOS) / PowerShell (Windows) |
| Daemon | launchd (macOS) / systemd (Linux) / Task Scheduler (Windows) |

---

## Getting Started

### Prerequisites
- Python 3.11+
- macOS, Windows, or Linux
- Google Chrome or Safari (for browser control)

### Installation

```bash
git clone https://github.com/ShadowKingYT444/JarvisAi.git
cd JarvisAi

# Install dependencies
pip install -r jarvis/requirements.txt

# Run the installer (creates ~/.jarvis, config, and auto-start)
jarvis install
```

### API Keys

Edit `~/.jarvis/.env` with your keys:
```env
GOOGLE_API_KEY=your_gemini_api_key
SEARCH_API_KEY=your_google_cse_or_serpapi_key
SEARCH_ENGINE_ID=your_google_cse_id
# ELEVENLABS_API_KEY=optional_premium_tts
```

### Usage

```bash
jarvis start              # Start the daemon (background)
jarvis start --test       # Text mode (stdin, no mic)
jarvis stop               # Stop the daemon
jarvis status             # Check daemon status
jarvis text "open spotify"  # Send a text command
jarvis calibrate          # Re-calibrate clap detection
jarvis config             # Edit configuration
jarvis log                # Tail today's conversation log
```

---

## How It Works

1. **Double-clap** activates Jarvis (replaces wake word for privacy)
2. **Faster-Whisper** transcribes your voice command locally
3. **Gemini 2.0 Flash** decides which tools to call via function calling
4. **Tools execute**: search the web, open tabs/apps, control system
5. **Jarvis speaks** a concise summary and opens sources in your browser

### Example Commands

| Command | What Happens |
|---------|-------------|
| "What's going on in the world?" | Searches news, opens top 3 tabs, speaks summary |
| "Open Spotify" | Launches Spotify via system command |
| "Focus on writing my essay" | Starts focus mode, monitors/closes distracting tabs |
| "Set a reminder in 30 minutes to stretch" | Sets timed reminder with TTS alert |
| "Take a screenshot" | Captures screen to Desktop |
| "Read my clipboard" | Reads clipboard contents aloud |

---

## Project Structure

```
jarvis/
├── shared/          # Shared types, events, config
├── activation/      # Double-clap detection + mic manager
├── ears/            # Speech-to-text (faster-whisper)
├── brain/           # Gemini orchestrator + tool definitions
├── hands/           # Tool executor + platform abstraction
│   └── tools/       # web_search, browser, apps, focus_mode, etc.
├── voice/           # TTS engine + speech queue
├── face/            # System tray + overlay HUD
├── daemon/          # Background service + CLI + installer
└── tests/           # Unit + integration tests
```

---

## Configuration

Config file: `~/.jarvis/config.yaml`

```yaml
gemini_model: gemini-2.0-flash
whisper_model_size: base.en    # tiny.en, small.en, medium.en
tts_engine: macos_say          # macos_say, elevenlabs, pyttsx3
tts_voice: Daniel
tts_rate: 180
clap_sensitivity: 0.7
search_provider: google_cse    # google_cse, serpapi
focus_check_interval_s: 30
```

---

## Testing

```bash
# Run all tests
cd jarvis && python -m pytest tests/ -v

# Run specific test suites
python -m pytest tests/test_activation.py -v
python -m pytest tests/test_hands.py -v
python -m pytest tests/test_brain.py -v
python -m pytest tests/test_integration.py -v
```

---

## Tech Stack

- **LLM**: Google Gemini 2.0 Flash (function calling)
- **STT**: Faster-Whisper (local, int8 quantization)
- **TTS**: macOS say / ElevenLabs / pyttsx3
- **Audio**: sounddevice, scipy, webrtcvad
- **GUI**: PyQt6 + qasync
- **Search**: Google Custom Search / SerpAPI
- **Daemon**: launchd / systemd / Task Scheduler
