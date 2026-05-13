"""Audio URL and local-file handling."""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import AUDIO_CACHE_DIR, ensure_dirs

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]


class SourceError(Exception):
    pass


def _http_session() -> requests.Session:
    """Return a ``requests.Session`` with automatic retry on transient errors."""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name or parsed.netloc or "remote-audio"
    return name.rsplit(".", 1)[0]


def _duration_ms(path: Path) -> int:
    try:
        from mutagen import File
        media = File(str(path))
        if media is not None and media.info and getattr(media.info, "length", None):
            return int(float(media.info.length) * 1000)
    except Exception:
        logger.debug("mutagen.File failed for %s", path, exc_info=True)
    try:
        from mutagen.mp3 import MP3
        media = MP3(str(path))
        if media is not None and media.info and getattr(media.info, "length", None):
            return int(float(media.info.length) * 1000)
    except Exception:
        logger.debug("mutagen.mp3 fallback failed for %s", path, exc_info=True)
        return 0
    return 0


def register_local_file(path_value: str) -> dict:
    ensure_dirs()
    source_path = Path(path_value)
    if not source_path.exists() or not source_path.is_file():
        raise SourceError("找不到本地音訊檔。")
    audio_hash = _sha1_file(source_path)
    cached_path = AUDIO_CACHE_DIR / f"{audio_hash}{source_path.suffix.lower() or '.mp3'}"
    if not cached_path.exists():
        shutil.copy2(source_path, cached_path)
    return {
        "id": audio_hash,
        "source_type": "file",
        "source_url": "",
        "original_path": str(source_path),
        "local_path": str(cached_path),
        "title": source_path.stem,
        "duration_ms": _duration_ms(cached_path),
        "analysis_status": "not_started",
        "created_ts": int(time.time()),
    }


def download_url(url: str, on_progress: ProgressCallback | None = None) -> dict:
    ensure_dirs()
    cleaned_url = str(url or "").strip()
    parsed = urlparse(cleaned_url)
    if parsed.scheme not in {"http", "https"}:
        raise SourceError("請輸入有效的 http 或 https MP3 網址。")
    if on_progress:
        on_progress("連線到音訊來源...")
    session = _http_session()
    try:
        response = session.get(cleaned_url, stream=True, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SourceError(f"下載音訊失敗：{exc}") from exc

    suffix = Path(parsed.path).suffix.lower() or ".mp3"
    temp_path = AUDIO_CACHE_DIR / f"download-{int(time.time())}.tmp"
    total_bytes = int(response.headers.get("content-length") or 0)
    downloaded = 0
    with open(temp_path, "wb") as file_obj:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if not chunk:
                continue
            file_obj.write(chunk)
            downloaded += len(chunk)
            if on_progress and total_bytes:
                percent = int((downloaded / total_bytes) * 100)
                on_progress(f"下載音訊中... {percent}%")

    # Verify download completeness when Content-Length was provided
    if total_bytes and downloaded != total_bytes:
        temp_path.unlink(missing_ok=True)
        raise SourceError(
            f"下載不完整：預期 {total_bytes} 位元組，實際收到 {downloaded} 位元組。"
        )

    audio_hash = _sha1_file(temp_path)
    cached_path = AUDIO_CACHE_DIR / f"{audio_hash}{suffix}"
    if cached_path.exists():
        temp_path.unlink(missing_ok=True)
    else:
        temp_path.replace(cached_path)

    return {
        "id": audio_hash,
        "source_type": "url",
        "source_url": cleaned_url,
        "original_path": "",
        "local_path": str(cached_path),
        "title": _title_from_url(cleaned_url),
        "duration_ms": _duration_ms(cached_path),
        "analysis_status": "not_started",
        "created_ts": int(time.time()),
    }