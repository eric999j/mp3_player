"""Application configuration and data paths."""
from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "Mp3InsightPlayer"


def _appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / APP_NAME


DATA_DIR: Path = _appdata_dir()
AUDIO_CACHE_DIR: Path = DATA_DIR / "audio_cache"
EXPORT_DIR: Path = DATA_DIR / "exports"
SETTINGS_FILE: Path = DATA_DIR / "settings.json"
LIBRARY_FILE: Path = DATA_DIR / "library.json"
TRANSCRIPT_FILE: Path = DATA_DIR / "transcripts.json"
ANALYSIS_FILE: Path = DATA_DIR / "analysis.json"

WINDOW_GEOMETRY = "1120x760"
DEFAULT_ASR_MODEL = "tiny"
DEFAULT_CHAT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
HF_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"

# Local faster-whisper model sizes (downloaded on first use)
AVAILABLE_ASR_MODELS = [
    "tiny",
    "base",
    "small",
    "medium",
    "large-v3",
]

AVAILABLE_CHAT_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "google/gemma-2-9b-it",
]

# Language choices for transcription; "auto" lets faster-whisper detect.
AVAILABLE_LANGUAGES = [
    ("自動偵測", "auto"),
    ("中文", "zh"),
    ("English", "en"),
    ("日本語", "ja"),
    ("한국어", "ko"),
]


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)