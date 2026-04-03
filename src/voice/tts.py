# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# https://www.gnu.org/licenses/gpl-3.0.html
"""
TTS через Piper (оффлайн нейросетевой синтез речи, Linux/ARM).
Если piper не найден или модель отсутствует — вывод фраз в консоль (fallback).

Установка piper:  pip install piper-tts
Модель (ru_RU-ruslan-medium):
  https://huggingface.co/rhasspy/piper-voices/tree/main/ru/ru_RU/ruslan/medium
  Скачать .onnx и .onnx.json в models/
"""
import shutil
import subprocess
import sys
import threading
from typing import Optional

from src.config import AUDIO_OUTPUT_DEVICE, PIPER_MODEL_PATH, PIPER_SAMPLE_RATE


def _find_piper() -> Optional[str]:
    """Найти исполняемый файл piper в PATH."""
    return shutil.which("piper")


class TTS:
    def __init__(self, output_device_id: Optional[int] = None) -> None:
        self._piper_bin = _find_piper()
        self._model = PIPER_MODEL_PATH
        self._sample_rate = PIPER_SAMPLE_RATE
        self._device_id = output_device_id
        if AUDIO_OUTPUT_DEVICE is not None:
            try:
                self._device_id = int(AUDIO_OUTPUT_DEVICE)
            except ValueError:
                pass

        if not self._piper_bin:
            print(
                "TTS: piper не найден в PATH. Установите: pip install piper-tts",
                file=sys.stderr,
            )
        elif not self._model.exists():
            print(
                f"TTS: модель piper не найдена: {self._model}",
                file=sys.stderr,
            )
            print(
                "Скачайте .onnx и .onnx.json с "
                "https://huggingface.co/rhasspy/piper-voices/",
                file=sys.stderr,
            )

    def is_available(self) -> bool:
        """True, если piper и модель доступны (иначе только вывод в консоль)."""
        return bool(self._piper_bin and self._model.exists())

    def say(self, text: str, block: bool = True) -> None:
        """Озвучить текст. block=True — дождаться окончания."""
        if not text or not text.strip():
            return
        text = text.strip()
        print(f"[TTS] {text}", flush=True)
        if not self.is_available():
            return

        def _play() -> None:
            try:
                import numpy as np
                import sounddevice as sd
            except ImportError as e:
                print(f"TTS: не удалось импортировать numpy/sounddevice: {e}", file=sys.stderr)
                return
            try:
                result = subprocess.run(
                    [self._piper_bin, "--model", str(self._model), "--output_raw"],
                    input=text.encode("utf-8"),
                    capture_output=True,
                    timeout=30,
                )
                if result.returncode == 0 and result.stdout:
                    audio = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0
                    sd.play(audio, samplerate=self._sample_rate, device=self._device_id, blocking=True)
                elif result.stderr:
                    print(
                        f"TTS piper: {result.stderr.decode(errors='replace').strip()}",
                        file=sys.stderr,
                    )
            except subprocess.TimeoutExpired:
                print("TTS: таймаут piper.", file=sys.stderr)
            except Exception as e:
                print(f"TTS: ошибка воспроизведения — {e}", file=sys.stderr)
                # Помечаем что аудио недоступно — дальше только консоль
                self._piper_bin = None

        if block:
            _play()
        else:
            threading.Thread(target=_play, daemon=True).start()

    def stop(self) -> None:
        """Остановить воспроизведение."""
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    def shutdown(self) -> None:
        """Освободить ресурсы."""
        self.stop()
