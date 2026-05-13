"""Local ASR (faster-whisper) and Hugging Face chat analysis."""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from faster_whisper import WhisperModel

from .analysis import align_model_analysis, estimate_chunks, local_keyword_analysis
from .config import HF_ROUTER_URL
from .prompts import ANALYSIS_SYSTEM_PROMPT, build_analysis_prompt

logger = logging.getLogger(__name__)

_whisper_cache: dict[str, WhisperModel] = {}

_StatusCallback = Callable[[str], None] | None


class APIError(Exception):
    pass


def _http_session() -> requests.Session:
    """Return a ``requests.Session`` with automatic retry on transient errors."""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text or "", flags=re.IGNORECASE)
    decoder = json.JSONDecoder()
    # Find the first valid JSON object in the text
    for i, ch in enumerate(cleaned):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(cleaned, i)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    raise APIError(f"模型輸出找不到 JSON：{cleaned[:200]}")


def _is_model_cached(model_size: str) -> bool:
    """Check whether the faster-whisper model files are already in the local HF cache."""
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    model_dir = cache_dir / f"models--Systran--faster-whisper-{model_size}"
    return model_dir.exists()


def _get_whisper_model(model_size: str, status_callback: _StatusCallback = None) -> WhisperModel:
    """Get or create a cached WhisperModel instance, reporting download progress via callback."""
    if model_size not in _whisper_cache:
        if not _is_model_cached(model_size):
            _notify(status_callback, f"正在下載 Whisper {model_size} 模型（首次使用，依網速可能需數分鐘）...")
        else:
            _notify(status_callback, f"載入 Whisper {model_size} 模型...")
        _whisper_cache[model_size] = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
        )
    return _whisper_cache[model_size]


def _notify(callback: _StatusCallback, message: str) -> None:
    if callable(callback):
        try:
            callback(message)
        except (TypeError, RuntimeError):
            pass


# Minimum seconds between throttled progress notifications sent to the UI thread.
# Keeps the Tkinter event queue clear so playback stays smooth.
_PROGRESS_THROTTLE_S = 2.0


def transcribe_audio(
    *,
    hf_token: str,
    asr_model: str,
    audio_path: str,
    duration_ms: int,
    status_callback: _StatusCallback = None,
    language: str = "auto",
) -> dict[str, Any]:
    """Transcribe audio using local faster-whisper (CPU, int8).

    Runs entirely in the caller's thread (should be a daemon worker thread).
    Progress notifications are throttled to at most one every 2 s so the
    Tkinter main-loop / pygame playback thread remain responsive.

    When *language* is ``"auto"`` (default), faster-whisper auto-detects the
    spoken language.  Otherwise pass a two-letter ISO 639-1 code like ``"zh"``.
    """
    path = Path(audio_path)
    if not path.exists():
        raise APIError("找不到要轉錄的音訊快取檔。")

    model_size = str(asr_model or "tiny").strip()
    try:
        model = _get_whisper_model(model_size, status_callback)
    except Exception as exc:
        raise APIError(f"載入 Whisper 模型 '{model_size}' 失敗：{exc}") from exc

    _notify(status_callback, f"轉錄音訊中（Whisper {model_size}，較長音檔需要幾分鐘）...")

    lang_code = str(language or "auto").strip()
    transcribe_kwargs: dict[str, Any] = {
        "beam_size": 5,
        "vad_filter": True,
    }
    if lang_code and lang_code != "auto":
        transcribe_kwargs["language"] = lang_code

    try:
        segments_iter, info = model.transcribe(
            str(path),
            **transcribe_kwargs,
        )
    except Exception as exc:
        raise APIError(f"轉錄失敗：{exc}") from exc

    detected_lang = getattr(info, "language", lang_code if lang_code != "auto" else "unknown")
    if lang_code == "auto":
        _notify(status_callback, f"偵測到語言：{detected_lang}，轉錄中...")

    chunks: list[dict[str, Any]] = []
    total_sec = duration_ms / 1000 if duration_ms else 0
    _last_notify = 0.0  # wall-clock time of last progress notification
    _last_pct = -1

    for segment in segments_iter:
        # Segment iteration IS the transcription work — happens in this background thread.
        text = segment.text.strip()
        if text:
            chunks.append({
                "start_ms": int(segment.start * 1000),
                "end_ms": int(segment.end * 1000),
                "text": text,
            })

        # Throttle UI notifications: send at most one update every _PROGRESS_THROTTLE_S
        # seconds to keep the Tkinter event queue clear for smooth playback.
        if total_sec > 0:
            pct = min(int(segment.end / total_sec * 100), 99)
            now = time.monotonic()
            if pct != _last_pct and (now - _last_notify) >= _PROGRESS_THROTTLE_S:
                elapsed_min = int(segment.end // 60)
                total_min = int(total_sec // 60)
                _notify(status_callback, f"轉錄進度 {pct}%（{elapsed_min}/{total_min} 分鐘）...")
                _last_notify = now
                _last_pct = pct

    if not chunks:
        raise APIError("轉錄完成但沒有偵測到語音內容。")

    _notify(status_callback, "轉錄完成，準備分析關鍵詞...")
    full_text = "\n".join(chunk["text"] for chunk in chunks)
    return {
        "text": full_text,
        "chunks": chunks,
        "asr_model": f"faster-whisper ({model_size})",
        "language": detected_lang,
    }


def analyze_transcript(
    *,
    hf_token: str,
    chat_model: str,
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    transcript_text = "\n".join(str(chunk.get("text", "")) for chunk in chunks)
    if not transcript_text.strip():
        raise APIError("沒有可分析的逐字稿。")
    token = str(hf_token or "").strip()
    if not token:
        return local_keyword_analysis(chunks)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "model": chat_model,
        "messages": [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": build_analysis_prompt(transcript_text)},
        ],
        "temperature": 0.2,
        "max_tokens": 1800,
        "stream": False,
    }
    session = _http_session()
    try:
        response = session.post(HF_ROUTER_URL, headers=headers, json=payload, timeout=120)
        if response.status_code >= 400:
            logger.warning("HF API returned %d, falling back to local analysis", response.status_code)
            return local_keyword_analysis(chunks)
        data = response.json()
        content = str(data["choices"][0]["message"]["content"] or "")
        parsed = _extract_json(content)
        return align_model_analysis(parsed, chunks)
    except (requests.RequestException, APIError, KeyError, IndexError) as exc:
        logger.warning("HF analysis failed, falling back to local: %s", exc)
        return local_keyword_analysis(chunks)