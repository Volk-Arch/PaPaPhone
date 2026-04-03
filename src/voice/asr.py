# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# https://www.gnu.org/licenses/gpl-3.0.html
"""
Распознавание речи через Vosk: загрузка модели, запись с микрофона, потоковая выдача текста.
"""
import json
import queue
import threading
from pathlib import Path
from typing import Optional

import sounddevice as sd
from vosk import KaldiRecognizer, Model

from src.config import (
    BLOCK_SIZE_MS,
    CHANNELS,
    SAMPLE_RATE,
    VOSK_MODEL_PATH,
    AUDIO_INPUT_DEVICE,
)


class ASRError(Exception):
    """Ошибка ASR (модель не найдена, устройство записи и т.д.)."""


class ASR:
    """
    Обёртка над Vosk: непрерывная запись с микрофона и распознавание.
    listen() блокирует до получения одной фразы (или по таймауту).
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        sample_rate: int = SAMPLE_RATE,
        device: Optional[int] = None,
        block_ms: int = BLOCK_SIZE_MS,
    ) -> None:
        self.model_path = model_path or VOSK_MODEL_PATH
        self.sample_rate = sample_rate
        self.block_ms = block_ms
        self.block_size = (sample_rate * block_ms) // 1000
        if AUDIO_INPUT_DEVICE is not None:
            try:
                device = int(AUDIO_INPUT_DEVICE)
            except ValueError:
                pass
        self.device = device
        self._model: Optional[Model] = None
        self._recognizer: Optional[KaldiRecognizer] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def load_model(self) -> None:
        """Загрузить модель Vosk из папки."""
        if not self.model_path.exists():
            raise ASRError(f"Модель Vosk не найдена: {self.model_path}")
        self._model = Model(str(self.model_path))
        self._recognizer = KaldiRecognizer(self._model, self.sample_rate)
        self._recognizer.SetWords(True)

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            import sys
            print(f"[ASR] Аудио: {status}", file=sys.stderr)
        try:
            self._audio_queue.put(bytes(indata))
        except queue.Full:
            pass

    def start_stream(self) -> None:
        """Запустить захват аудио с микрофона в отдельном потоке."""
        if self._model is None:
            self.load_model()
        self._stop_event.clear()
        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            dtype="int16",
            channels=CHANNELS,
            device=self.device,
            callback=self._audio_callback,
        )
        self._stream.start()

    def stop_stream(self) -> None:
        """Остановить захват аудио."""
        self._stop_event.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def listen(self, timeout_s: float = 10.0) -> Optional[str]:
        """
        Слушать микрофон до первой распознанной фразы или таймаута.
        Возвращает текст фразы или None.
        При потере микрофона пытается переподключить стрим.
        """
        if self._recognizer is None:
            self.load_model()
        try:
            if self._stream is None or not self._stream.active:
                self.start_stream()
        except Exception as e:
            import sys
            print(f"[ASR] Не удалось открыть микрофон: {e}", file=sys.stderr)
            return None

        self._recognizer.Reset()
        phrase_parts = []
        import time
        deadline = time.monotonic() + timeout_s

        try:
            while time.monotonic() < deadline:
                try:
                    chunk = self._audio_queue.get(timeout=0.2)
                except queue.Empty:
                    chunk = None
                if chunk:
                    if self._recognizer.AcceptWaveform(chunk):
                        result = json.loads(self._recognizer.Result())
                        text = (result.get("text") or "").strip()
                        if text:
                            return text
                    else:
                        partial = json.loads(self._recognizer.PartialResult())
                        pt = (partial.get("partial") or "").strip()
                        if pt:
                            phrase_parts.append(pt)
                if self._stop_event.is_set():
                    break

            if phrase_parts:
                return phrase_parts[-1]
            result = json.loads(self._recognizer.FinalResult())
            text = (result.get("text") or "").strip()
            return text if text else None
        except Exception as e:
            import sys
            print(f"[ASR] Ошибка распознавания: {e}", file=sys.stderr)
            # Сбросить стрим — при следующем listen() попробует переоткрыть
            self.stop_stream()
            return None

    def shutdown(self) -> None:
        """Остановить поток и освободить ресурсы."""
        self.stop_stream()
        self._model = None
        self._recognizer = None
