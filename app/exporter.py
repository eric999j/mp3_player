"""Export transcript and analysis results."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import EXPORT_DIR, ensure_dirs
from .time_utils import format_ms


def export_markdown(source: dict[str, Any], transcript: dict[str, Any] | None, analysis: dict[str, Any] | None, save_path: Path | None = None) -> Path:
    ensure_dirs()
    title = str(source.get("title") or source.get("id") or "audio")
    safe_title = "".join(char if char.isalnum() or char in "-_" else "_" for char in title)[:80]
    path = save_path if save_path else EXPORT_DIR / f"{safe_title}.md"
    lines = [f"# {title}", ""]
    if source.get("source_url"):
        lines.extend([f"來源：{source.get('source_url')}", ""])
    if analysis:
        lines.extend(["## 摘要", "", str(analysis.get("summary", "")), ""])
        lines.extend(["## 關鍵詞", ""])
        for item in analysis.get("keywords", []) or []:
            if not isinstance(item, dict):
                continue
            timestamps = item.get("timestamps", []) or []
            first_time = format_ms(timestamps[0].get("start_ms", 0)) if timestamps else "--:--"
            lines.append(f"- [{first_time}] {item.get('term', '')} ({item.get('category', '其他')})：{item.get('reason', '')}")
        lines.extend(["", "## 重點句", ""])
        for item in analysis.get("highlights", []) or []:
            if isinstance(item, dict):
                lines.append(f"- [{format_ms(item.get('start_ms', 0))}] {item.get('text', '')}")
        actions = analysis.get("actions", []) or []
        if actions:
            lines.extend(["", "## 行動項目", ""])
            for action in actions:
                lines.append(f"- {action}")
    if transcript:
        lines.extend(["", "## 逐字稿", ""])
        for chunk in transcript.get("chunks", []) or []:
            if isinstance(chunk, dict):
                lines.append(f"[{format_ms(chunk.get('start_ms', 0))}] {chunk.get('text', '')}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export_json(source: dict[str, Any], transcript: dict[str, Any] | None, analysis: dict[str, Any] | None, save_path: Path | None = None) -> Path:
    ensure_dirs()
    title = str(source.get("title") or source.get("id") or "audio")
    safe_title = "".join(char if char.isalnum() or char in "-_" else "_" for char in title)[:80]
    path = save_path if save_path else EXPORT_DIR / f"{safe_title}.json"
    payload = {"source": source, "transcript": transcript, "analysis": analysis}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path