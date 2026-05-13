"""Time formatting helpers."""
from __future__ import annotations


def format_ms(value_ms: int | float | None) -> str:
    total_seconds = max(0, int((value_ms or 0) / 1000))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def parse_time_label(label: str) -> int:
    parts = [int(part) for part in str(label or "").split(":") if part.strip().isdigit()]
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    else:
        return 0
    return ((hours * 3600) + (minutes * 60) + seconds) * 1000