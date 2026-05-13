---
description: "Generate a focused smoke test checklist for MP3 Insight Player after code or dependency changes."
name: "Smoke Test MP3 Insight Player"
argument-hint: "Changed area or scenario to focus on, for example playback, URL loading, transcription, export, or theme settings"
agent: "agent"
---

Create a focused manual smoke test checklist for MP3 Insight Player.

Use the optional argument as the changed area or scenario to emphasize: `$ARGUMENTS`.

Before drafting the checklist, quickly inspect the relevant repository context:
- [AGENTS.md](../../AGENTS.md) for architecture, setup, runtime details, and validation expectations.
- [README.md](../../README.md) for user workflow and setup details.
- The current git changes, if any, to focus the smoke test on impacted behavior.

Generate the response in Traditional Chinese with these sections:

## Scope
- One short paragraph naming the feature area under test and any assumptions, such as GUI availability, VLC availability, Hugging Face token availability, and whether local sample MP3 files are available.

## Preflight
- Verify the environment is activated and dependencies are installed.
- Include the run command `python main.py`.
- Mention that generated app data lives under `%APPDATA%/Mp3InsightPlayer/` and should not be committed.

## Smoke Test Checklist
- Use checkbox bullets.
- Cover only the workflows relevant to the argument and current changes, plus a small set of app-critical basics.
- Include expected results for each step.
- Include negative/fallback checks when relevant, especially no Hugging Face token, VLC missing or pygame fallback, failed URL download, missing cache file, and local analysis fallback.
- Include responsiveness checks when background work is involved: the UI should remain usable, playback ticks should continue, and worker progress/status should update without direct Tkinter mutation from worker threads.

## Evidence To Capture
- List concise notes/screenshots/logs/state files the tester should record, if useful.

## Risks Not Covered
- Name anything the smoke test intentionally does not validate, such as full transcription accuracy, long-audio performance, or every model choice.

Keep the checklist compact enough to run manually in 5-15 minutes unless the argument asks for a deeper pass. Do not run the GUI or modify files unless the user explicitly asks you to execute the smoke test.