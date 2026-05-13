# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project Overview

MP3 Insight Player is a Windows-friendly Tkinter desktop app for loading local or remote MP3 files, playing them, transcribing them with local `faster-whisper`, analyzing transcripts through Hugging Face chat models when a token is configured, and exporting notes. For user setup and workflow details, link to [README.md](README.md) instead of duplicating it.

## Run And Setup

- Python 3.10+ is expected.
- Create/activate the local environment on Windows PowerShell with `python -m venv .venv`, `./.venv/Scripts/Activate.ps1`, then `pip install -r requirements.txt`.
- Start the app with `python main.py`.
- There is no formal test suite or CI configuration in the repo right now. For behavior changes, do a focused smoke check with `python main.py` when a GUI-capable environment is available.

## Architecture Map

- [main.py](main.py) is the entry point and delegates to `app.ui.run()`.
- [app/ui.py](app/ui.py) owns the Tkinter UI, tabs, theme behavior, playback controls, background worker orchestration, and user-facing Traditional Chinese strings.
- [app/player_engine.py](app/player_engine.py) wraps audio playback, preferring VLC through `python-vlc` and falling back to `pygame` when VLC is unavailable.
- [app/source_manager.py](app/source_manager.py) registers local files, downloads URLs, computes SHA1 audio IDs, and manages cached audio files.
- [app/api_client.py](app/api_client.py) runs local CPU `faster-whisper` transcription and Hugging Face Router chat analysis.
- [app/analysis.py](app/analysis.py) provides local keyword/highlight fallback logic and timestamp alignment.
- [app/storage.py](app/storage.py) persists settings, library entries, transcripts, and analysis JSON with atomic temp-file writes.
- [app/exporter.py](app/exporter.py) writes Markdown and JSON exports.
- [app/config.py](app/config.py) centralizes app data paths, model defaults, model choices, and constants.

## Important Runtime Details

- User data is stored under `%APPDATA%/Mp3InsightPlayer/`, including `audio_cache/`, `settings.json`, `library.json`, `transcripts.json`, `analysis.json`, and exports. Do not add generated runtime data to the repository.
- `faster-whisper` models are downloaded on first use into the user's Hugging Face cache and can take time, especially larger models. The default ASR model in code is `tiny`.
- Hugging Face tokens are optional for playback and transcription fallback paths. Never hard-code tokens or sample secrets; the app stores user settings locally.
- VLC may not be installed on every machine. Preserve the VLC-first / pygame-fallback behavior unless the requested change explicitly touches playback backend selection.

## Coding Conventions

- Keep changes small and module-scoped; this app has clear boundaries between UI, playback, source management, API/model calls, analysis, export, and storage.
- Match existing Python style: `from __future__ import annotations`, PEP 604 union types, typed function signatures where practical, and simple custom exceptions for module-specific failures.
- Keep UI text in Traditional Chinese unless the user requests otherwise.
- Long-running work should stay off the Tkinter main thread. Follow the existing daemon-thread and throttled status-callback pattern so playback and the UI remain responsive.
- Preserve UTF-8 JSON persistence with `ensure_ascii=False` and atomic `*.tmp` replacement writes.
- Prefer lazy or guarded imports for optional/system-sensitive dependencies such as VLC, pygame, and mutagen.

## Validation Notes

- For pure helper changes, use targeted Python imports or small manual checks rather than broad GUI smoke tests when that is enough.
- For playback, source loading, transcription, or UI changes, verify the relevant path manually if the environment can open Tkinter windows.
- If tests are added later, document the command here and keep it aligned with the chosen test runner.
