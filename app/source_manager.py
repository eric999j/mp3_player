"""Audio/video URL and local-file handling."""
from __future__ import annotations

import hashlib
import logging
import re
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

# Extensions that VLC and mutagen can treat as video sources.
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}

_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "youtu.be", "www.youtu.be",
    "music.youtube.com",
}


class SourceError(Exception):
    pass


def _is_youtube_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    return host in _YOUTUBE_HOSTS


def has_video(source: dict) -> bool:
    """Return True when the source likely contains a video track."""
    if str(source.get("source_type", "")) == "youtube":
        return True
    local_path = str(source.get("local_path") or "")
    if local_path and Path(local_path).suffix.lower() in VIDEO_EXTENSIONS:
        return True
    return False


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
    last_reported_percent = -1
    with open(temp_path, "wb") as file_obj:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if not chunk:
                continue
            file_obj.write(chunk)
            downloaded += len(chunk)
            if on_progress and total_bytes:
                percent = int((downloaded / total_bytes) * 100)
                if percent != last_reported_percent:
                    on_progress(f"下載音訊中... {percent}%")
                    last_reported_percent = percent

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


def load_url(url: str, on_progress: ProgressCallback | None = None) -> dict:
    """Dispatch a URL to the right fetcher (YouTube via yt-dlp, else direct download)."""
    if _is_youtube_url(url):
        return fetch_youtube(url, on_progress)
    return download_url(url, on_progress)


def fetch_youtube(url: str, on_progress: ProgressCallback | None = None) -> dict:
    """Download a YouTube video (video + audio muxed) via yt-dlp and register it."""
    ensure_dirs()
    cleaned_url = str(url or "").strip()
    if not cleaned_url:
        raise SourceError("請輸入 YouTube 網址。")

    try:
        import yt_dlp  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SourceError("需要 yt-dlp 才能播放 YouTube。請執行：pip install yt-dlp") from exc

    if on_progress:
        on_progress("正在解析 YouTube 網址...")

    info_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(cleaned_url, download=False)
    except yt_dlp.utils.DownloadError as exc:  # type: ignore[attr-defined]
        raise SourceError(f"無法讀取 YouTube 資訊：{exc}") from exc

    if isinstance(info, dict) and "entries" in info:
        entries = [entry for entry in info.get("entries") or [] if entry]
        if not entries:
            raise SourceError("YouTube 網址沒有可用的影片。")
        info = entries[0]

    video_id = str(info.get("id") or "").strip() or _fallback_video_id(cleaned_url)
    if not video_id:
        raise SourceError("無法辨識 YouTube 影片編號。")
    audio_id = f"yt-{video_id}"
    title = str(info.get("title") or video_id).strip() or video_id
    duration_ms = int((info.get("duration") or 0) * 1000)

    cached_existing = _find_cached_youtube_file(audio_id)
    if cached_existing is not None:
        if on_progress:
            on_progress("使用已快取的 YouTube 檔案")
        return _make_youtube_source(audio_id, cleaned_url, title, duration_ms, cached_existing)

    last_percent = {"value": -1}

    def hook(status: dict) -> None:
        if not on_progress:
            return
        state = status.get("status")
        if state == "downloading":
            downloaded = int(status.get("downloaded_bytes") or 0)
            total = int(status.get("total_bytes") or status.get("total_bytes_estimate") or 0)
            if total > 0:
                percent = int((downloaded / total) * 100)
                if percent != last_percent["value"]:
                    on_progress(f"下載 YouTube 影音中... {percent}%")
                    last_percent["value"] = percent
        elif state == "finished":
            on_progress("YouTube 下載完成，處理中...")

    output_template = str(AUDIO_CACHE_DIR / f"{audio_id}.%(ext)s")
    dl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": output_template,
        # Prefer pre-muxed <=720p mp4 to avoid an ffmpeg merge step; fall back gracefully.
        "format": "best[ext=mp4][height<=720]/best[height<=720]/best[ext=mp4]/best",
        "progress_hooks": [hook],
        "retries": 3,
        "fragment_retries": 3,
        "overwrites": False,
    }
    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            info = ydl.extract_info(cleaned_url, download=True)
    except yt_dlp.utils.DownloadError as exc:  # type: ignore[attr-defined]
        raise SourceError(f"YouTube 下載失敗：{exc}") from exc

    if isinstance(info, dict) and "entries" in info:
        entries = [entry for entry in info.get("entries") or [] if entry]
        if entries:
            info = entries[0]

    cached_path = _find_cached_youtube_file(audio_id)
    if cached_path is None:
        raise SourceError("YouTube 下載完成，但找不到檔案。")

    return _make_youtube_source(audio_id, cleaned_url, title, duration_ms, cached_path)


def _fallback_video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname and parsed.hostname.endswith("youtu.be"):
        return parsed.path.lstrip("/")
    for key in ("v",):
        match = re.search(rf"[?&]{key}=([^&#]+)", parsed.query)
        if match:
            return match.group(1)
    match = re.search(r"/shorts/([^/?#]+)", parsed.path)
    if match:
        return match.group(1)
    return ""


def _find_cached_youtube_file(audio_id: str) -> Path | None:
    for suffix in (".mp4", ".mkv", ".webm", ".m4a", ".mp3"):
        candidate = AUDIO_CACHE_DIR / f"{audio_id}{suffix}"
        if candidate.exists():
            return candidate
    for candidate in AUDIO_CACHE_DIR.glob(f"{audio_id}.*"):
        if candidate.is_file() and candidate.suffix.lower() not in {".part", ".tmp"}:
            return candidate
    return None


def _make_youtube_source(audio_id: str, url: str, title: str, duration_ms: int, cached_path: Path) -> dict:
    resolved_duration = duration_ms if duration_ms > 0 else _duration_ms(cached_path)
    return {
        "id": audio_id,
        "source_type": "youtube",
        "source_url": url,
        "original_path": "",
        "local_path": str(cached_path),
        "title": title,
        "duration_ms": resolved_duration,
        "analysis_status": "not_started",
        "created_ts": int(time.time()),
    }