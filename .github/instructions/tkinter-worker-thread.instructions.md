---
description: "Use when modifying Python Tkinter UI, background workers, threading, playback ticks, transcription, download, analysis, or status callbacks in MP3 Insight Player."
applyTo: "app/**/*.py"
---

# Tkinter Worker Thread Conventions

- Keep Tkinter UI work on the main thread. Worker threads may do downloads, file hashing, `faster-whisper` transcription, Hugging Face analysis, storage updates, or other slow work, but they must not directly mutate widgets, `StringVar`/`DoubleVar` values, dialogs, notebooks, treeviews, or listboxes.
- Use `self.root.after(0, callback, *args)` to hand UI updates back to Tkinter from a worker. This includes success callbacks, error dialogs, status text, tab selection, list/tree refreshes, and transcript/analysis rendering.
- For reusable short jobs, prefer the existing `_run_background(label, work, on_success)` pattern in `app/ui.py`. For multi-step jobs like analysis, follow the local `worker()` plus `threading.Thread(target=worker, daemon=True).start()` pattern.
- Use `daemon=True` for background threads so the desktop app can close cleanly after `WM_DELETE_WINDOW` releases the player and destroys the root window.
- Route progress from worker-owned APIs through a callback that schedules UI work, such as `_thread_status()`. Keep frequent progress messages throttled in lower-level code when work can emit many updates.
- Do not block the Tkinter event loop with network requests, model loading, transcription, audio hashing, export work, or long storage operations. If a user action can take noticeable time, move it behind a worker and show status in Traditional Chinese.
- Preserve playback responsiveness: keep `_update_player_tick()` lightweight and scheduled with `root.after(...)`; avoid adding heavy computation, file I/O, or network calls to recurring UI ticks.
- Store durable state through `app/storage.py` helpers from the worker when appropriate, then schedule UI refreshes on the main thread. Preserve atomic JSON writes and `ensure_ascii=False` behavior.
- In exception paths inside workers, update persisted failure state first when relevant, then schedule user-visible status and `messagebox` calls through `root.after(0, ...)`.
- Keep user-facing UI strings in Traditional Chinese unless the requested change explicitly asks for another locale.
