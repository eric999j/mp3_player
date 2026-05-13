"""MP3 playback engine with VLC first and pygame fallback."""
from __future__ import annotations

import time
from pathlib import Path


class PlayerError(Exception):
    pass


class Mp3Player:
    def __init__(self) -> None:
        self._backend = "vlc"
        try:
            import vlc
        except Exception as exc:
            self._init_pygame(exc)
            return
        try:
            self._vlc = vlc
            self._instance = vlc.Instance()
            self._player = self._instance.media_player_new()
        except Exception as exc:
            self._init_pygame(exc)
            return
        self._loaded_source = ""

    def _init_pygame(self, original_error: Exception) -> None:
        try:
            import pygame
            pygame.mixer.init()
        except Exception as exc:
            raise PlayerError(
                "缺少可用播放環境。請安裝 VLC media player，或確認 pygame mixer 可初始化。"
            ) from exc
        self._backend = "pygame"
        self._pygame = pygame
        self._loaded_source = ""
        self._duration_ms = 0
        self._start_offset_ms = 0
        self._play_started_at = 0.0
        self._paused = False
        self._paused_position_ms = 0
        self._original_error = original_error

    def load(self, source: str) -> None:
        if not source:
            raise PlayerError("尚未指定音訊來源。")
        source_value = str(Path(source)) if Path(source).exists() else source
        if self._backend == "pygame":
            if not Path(source_value).exists():
                raise PlayerError("pygame 備援播放器只能播放本地快取音訊。")
            self._pygame.mixer.music.load(source_value)
            self._loaded_source = source_value
            self._duration_ms = self._read_duration_ms(source_value)
            self._start_offset_ms = 0
            self._paused_position_ms = 0
            return
        media = self._instance.media_new(source_value)
        self._player.set_media(media)
        self._loaded_source = source_value

    def play(self) -> None:
        if not self._loaded_source:
            raise PlayerError("請先載入音訊。")
        if self._backend == "pygame":
            if self._paused:
                self._pygame.mixer.music.unpause()
                self._paused = False
                self._play_started_at = time.monotonic() - (self._paused_position_ms - self._start_offset_ms) / 1000
                return
            if self._duration_ms and self._start_offset_ms >= self._duration_ms - 1000:
                self._start_offset_ms = 0
            try:
                self._pygame.mixer.music.play(start=self._start_offset_ms / 1000)
            except Exception:
                self._start_offset_ms = 0
                self._pygame.mixer.music.play()
            self._play_started_at = time.monotonic()
            self._paused = False
            return
        result = self._player.play()
        if result == -1:
            raise PlayerError("VLC 無法播放此音訊。")

    def pause(self) -> None:
        if self._backend == "pygame":
            if self._paused:
                self._pygame.mixer.music.unpause()
                self._paused = False
                self._play_started_at = time.monotonic() - (self._paused_position_ms - self._start_offset_ms) / 1000
            else:
                self._paused_position_ms = self.get_position_ms()
                self._pygame.mixer.music.pause()
                self._paused = True
            return
        self._player.pause()

    def stop(self) -> None:
        if self._backend == "pygame":
            self._pygame.mixer.music.stop()
            self._start_offset_ms = 0
            self._paused_position_ms = 0
            self._paused = False
            return
        self._player.stop()

    def seek(self, position_ms: int) -> None:
        if self._backend == "pygame":
            target = max(0, int(position_ms))
            if self._duration_ms:
                target = min(target, max(0, self._duration_ms - 500))
            self._start_offset_ms = target
            self._paused_position_ms = self._start_offset_ms
            if self._pygame.mixer.music.get_busy() and not self._paused:
                try:
                    self._pygame.mixer.music.play(start=self._start_offset_ms / 1000)
                except Exception:
                    self._start_offset_ms = 0
                    self._pygame.mixer.music.play()
                self._play_started_at = time.monotonic()
            return
        self._player.set_time(max(0, int(position_ms)))

    def set_volume(self, volume: int) -> None:
        if self._backend == "pygame":
            self._pygame.mixer.music.set_volume(max(0, min(100, int(volume))) / 100)
            return
        self._player.audio_set_volume(max(0, min(100, int(volume))))

    def get_position_ms(self) -> int:
        if self._backend == "pygame":
            if self._paused:
                return self._paused_position_ms
            if not self._pygame.mixer.music.get_busy():
                return min(self._start_offset_ms, self._duration_ms) if self._duration_ms else self._start_offset_ms
            elapsed_ms = int((time.monotonic() - self._play_started_at) * 1000)
            position = self._start_offset_ms + elapsed_ms
            return min(position, self._duration_ms) if self._duration_ms else position
        value = self._player.get_time()
        return max(0, int(value or 0))

    def get_duration_ms(self) -> int:
        if self._backend == "pygame":
            return max(0, int(self._duration_ms or 0))
        value = self._player.get_length()
        return max(0, int(value or 0))

    def is_playing(self) -> bool:
        if self._backend == "pygame":
            return bool(self._pygame.mixer.music.get_busy() and not self._paused)
        return bool(self._player.is_playing())

    def release(self) -> None:
        try:
            self.stop()
            if self._backend == "pygame":
                self._pygame.mixer.quit()
                return
            self._player.release()
            self._instance.release()
        except Exception:
            pass

    def backend_name(self) -> str:
        return self._backend

    def _read_duration_ms(self, source: str) -> int:
        try:
            from mutagen import File
            media = File(source)
            if media is not None and media.info and getattr(media.info, "length", None):
                return int(float(media.info.length) * 1000)
        except Exception:
            pass
        try:
            from mutagen.mp3 import MP3
            media = MP3(source)
            if media is not None and media.info and getattr(media.info, "length", None):
                return int(float(media.info.length) * 1000)
        except Exception:
            return 0
        return 0