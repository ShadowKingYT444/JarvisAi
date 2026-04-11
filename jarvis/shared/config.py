"""Jarvis configuration loader and defaults."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class JarvisConfig:
    # LLM
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # STT
    whisper_model_size: str = "base.en"

    # TTS
    tts_engine: str = "auto"  # "auto" | "macos_say" | "elevenlabs" | "pyttsx3"
    tts_voice: str = "Daniel"
    tts_rate: int = 180
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""

    # Search
    search_provider: str = "auto"  # "auto" | "google_cse" | "serpapi"
    search_api_key: str = ""
    search_engine_id: str = ""

    # Activation
    clap_sensitivity: float = 0.7
    clap_timeout_ms: int = 600
    listen_timeout_s: int = 5
    max_record_s: int = 15
    audio_input_device: int | None = None  # None = system default
    activation_methods: list[str] = field(default_factory=lambda: ["clap", "hotkey"])
    wake_word_keyword: str = "jarvis"
    porcupine_access_key: str = ""
    hotkey: str = "ctrl+shift+j"

    # Focus Mode
    focus_check_interval_s: int = 30
    focus_warn_before_close_s: int = 10

    # Performance
    keep_model_loaded: bool = False  # Keep Whisper model in RAM between uses
    headless: bool = False  # Skip GUI initialization entirely

    # Paths
    jarvis_home: str = "~/.jarvis"
    log_dir: str = "~/.jarvis/logs"
    conversation_dir: str = "~/.jarvis/conversations"

    # App aliases for fuzzy matching
    app_aliases: dict = field(default_factory=lambda: {
        "vscode": "Visual Studio Code",
        "code": "Visual Studio Code",
        "chrome": "Google Chrome",
        "firefox": "Firefox",
        "safari": "Safari",
        "slack": "Slack",
        "spotify": "Spotify",
        "terminal": "Terminal",
        "finder": "Finder",
        "notes": "Notes",
        "messages": "Messages",
        "mail": "Mail",
        "calendar": "Calendar",
        "discord": "Discord",
        "zoom": "zoom.us",
        "teams": "Microsoft Teams",
        "word": "Microsoft Word",
        "excel": "Microsoft Excel",
        "powerpoint": "Microsoft PowerPoint",
    })

    @classmethod
    def load(cls, path: str = "~/.jarvis/config.yaml") -> "JarvisConfig":
        """Load config from YAML file, falling back to env vars and defaults."""
        expanded = Path(path).expanduser()

        config_data = {}
        if expanded.exists():
            with open(expanded) as f:
                config_data = yaml.safe_load(f) or {}

        # Load .env from jarvis home
        env_path = Path(config_data.get("jarvis_home", "~/.jarvis")).expanduser() / ".env"
        if env_path.exists():
            load_dotenv(env_path)

        # Env vars override config file
        config_data.setdefault("gemini_api_key", os.getenv("GOOGLE_API_KEY", ""))
        config_data.setdefault("search_api_key", os.getenv("SEARCH_API_KEY", ""))
        config_data.setdefault("search_engine_id", os.getenv("SEARCH_ENGINE_ID", ""))
        config_data.setdefault("elevenlabs_api_key", os.getenv("ELEVENLABS_API_KEY", ""))
        config_data.setdefault("porcupine_access_key", os.getenv("PORCUPINE_ACCESS_KEY", ""))

        # Build config, ignoring unknown keys
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in config_data.items() if k in valid_fields}
        return cls(**filtered)

    def save(self, path: str = "~/.jarvis/config.yaml") -> None:
        """Save current config to YAML file."""
        expanded = Path(path).expanduser()
        expanded.parent.mkdir(parents=True, exist_ok=True)

        from dataclasses import asdict
        data = asdict(self)
        # Don't persist secrets to YAML
        for secret_key in ("gemini_api_key", "search_api_key", "elevenlabs_api_key", "porcupine_access_key"):
            data.pop(secret_key, None)

        with open(expanded, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def save_env(self, path: str = "~/.jarvis/.env") -> None:
        """Write secret fields to the .env file."""
        expanded = Path(path).expanduser()
        expanded.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# Jarvis API Keys",
            f"GOOGLE_API_KEY={self.gemini_api_key}",
        ]
        if self.search_api_key:
            lines.append(f"SEARCH_API_KEY={self.search_api_key}")
        if self.search_engine_id:
            lines.append(f"SEARCH_ENGINE_ID={self.search_engine_id}")
        if self.elevenlabs_api_key:
            lines.append(f"ELEVENLABS_API_KEY={self.elevenlabs_api_key}")
        if self.porcupine_access_key:
            lines.append(f"PORCUPINE_ACCESS_KEY={self.porcupine_access_key}")

        expanded.write_text("\n".join(lines) + "\n")
        try:
            expanded.chmod(0o600)
        except OSError:
            pass  # Windows doesn't support Unix permissions

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        for dir_path in (self.jarvis_home, self.log_dir, self.conversation_dir):
            Path(dir_path).expanduser().mkdir(parents=True, exist_ok=True)

        # Also create backups dir
        (Path(self.jarvis_home).expanduser() / "backups").mkdir(parents=True, exist_ok=True)
