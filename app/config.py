"""
Central configuration loader.

Everything that varies between machines or environments (API keys, paths,
limits) lives here, read once from .env. Nothing else in the codebase
should call os.environ directly -- import `config` instead so there is
exactly one place to look when a setting needs to change.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    return int(val) if val else default


def _env_list(key: str) -> list[str]:
    raw = os.environ.get(key, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# --- Gemini ---
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.0-flash")

# --- Ollama ---
OLLAMA_HOST = _env("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "qwen3:4b")
OLLAMA_TIMEOUT_S = _env_int("OLLAMA_TIMEOUT_S", 60)

# --- Telegram ---
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_AUTHORIZED_CHAT_IDS = set(_env_list("TELEGRAM_AUTHORIZED_CHAT_IDS"))
TELEGRAM_AUTHORIZED_USER_IDS = set(_env_list("TELEGRAM_AUTHORIZED_USER_IDS"))

# --- Discord ---
DISCORD_BOT_TOKEN = _env("DISCORD_BOT_TOKEN")
DISCORD_AUTHORIZED_CHANNEL_IDS = set(_env_list("DISCORD_AUTHORIZED_CHANNEL_IDS"))
DISCORD_AUTHORIZED_USER_IDS = set(_env_list("DISCORD_AUTHORIZED_USER_IDS"))
ALLOW_OPEN_ACCESS = _env_bool("ALLOW_OPEN_ACCESS", False)
DELIVERY_CLAIM_TIMEOUT_S = _env_int("DELIVERY_CLAIM_TIMEOUT_S", 120)

# --- Paths (resolved to absolute paths relative to project root) ---
WATCH_FOLDER_PATH = BASE_DIR / _env("WATCH_FOLDER_PATH", "./watch_folder").lstrip("./")
PREVIEW_FOLDER_PATH = BASE_DIR / _env("PREVIEW_FOLDER_PATH", "./output/previews").lstrip("./")
APPROVED_FOLDER_PATH = BASE_DIR / _env("APPROVED_FOLDER_PATH", "./output/approved").lstrip("./")
DATABASE_PATH = BASE_DIR / _env("DATABASE_PATH", "./data/tekihelp.db").lstrip("./")
CALENDAR_PATH = BASE_DIR / _env("CALENDAR_PATH", "./data/calendar.json").lstrip("./")

for _p in (WATCH_FOLDER_PATH, PREVIEW_FOLDER_PATH, APPROVED_FOLDER_PATH, DATABASE_PATH.parent):
    _p.mkdir(parents=True, exist_ok=True)

# --- Agent safety ---
MAX_AGENT_ITERATIONS = _env_int("MAX_AGENT_ITERATIONS", 6)
