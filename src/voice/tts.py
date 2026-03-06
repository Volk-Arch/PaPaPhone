"""
Озвучка текста через pyttsx3 (eSpeak на Linux, SAPI на Windows).
Один экземпляр движка для избежания задержек при повторных вызовах.
При недоступности движка — вывод фраз в консоль (fallback).
"""
import sys
import threading
from typing import Optional

from src.config import AUDIO_OUTPUT_DEVICE

# Максимум секунд ожидания озвучки (на Windows runAndWait иногда зависает)
TTS_WAIT_TIMEOUT = 20.0


def _create_engine():
    """Инициализация с перебором драйверов и fallback."""
    try:
        import pyttsx3
    except Exception as e:
        print(f"TTS: не удалось импортировать pyttsx3: {e}", file=sys.stderr)
        return None
    err = None
    try:
        engine = pyttsx3.init()
        return engine
    except Exception as e1:
        err = e1
    for driver in ("sapi5", "espeak", "nsss"):
        try:
            engine = pyttsx3.init(driverName=driver)
            return engine
        except Exception:
            continue
    print(f"TTS: не удалось инициализировать движок ({err}). Установите espeak (Linux) или проверьте голоса Windows.", file=sys.stderr)
    return None


class TTS:
    def __init__(
        self,
        rate: int = 150,
        volume: float = 0.9,
        output_device_id: Optional[int] = None,
    ) -> None:
        self._engine = _create_engine()
        self._rate = rate
        self._volume = volume
        self._device_id = output_device_id
        if AUDIO_OUTPUT_DEVICE is not None:
            try:
                self._device_id = int(AUDIO_OUTPUT_DEVICE)
            except ValueError:
                pass
        if self._engine is not None:
            try:
                self._engine.setProperty("rate", self._rate)
                self._engine.setProperty("volume", self._volume)
            except Exception:
                pass
        self._using_engine = self._engine is not None

    def _get_engine(self):
        return self._engine

    def is_available(self) -> bool:
        """True, если озвучка через движок доступна (иначе только вывод в консоль)."""
        return getattr(self, "_using_engine", False)

    def say(self, text: str, block: bool = True) -> None:
        """Озвучить текст. block=True — дождаться окончания. При отсутствии движка — вывод в консоль."""
        if not text or not text.strip():
            return
        text = text.strip()
        # Сначала всегда выводим в консоль — чтобы ответ был виден даже если озвучка зависла или недоступна
        print(f"[TTS] {text}", flush=True)
        engine = self._get_engine()
        if engine is not None:
            try:
                engine.say(text)
                if block:
                    # runAndWait() на Windows иногда зависает — ограничиваем ожидание
                    done = threading.Event()
                    def run():
                        try:
                            engine.runAndWait()
                        except Exception:
                            pass
                        done.set()
                    t = threading.Thread(target=run, daemon=True)
                    t.start()
                    if not done.wait(timeout=TTS_WAIT_TIMEOUT):
                        print("TTS: таймаут озвучки, продолжаем.", file=sys.stderr)
            except Exception as e:
                print(f"TTS: ошибка озвучки — {e}", file=sys.stderr)

    def stop(self) -> None:
        """Остановить текущее воспроизведение."""
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass

    def shutdown(self) -> None:
        """Освободить ресурсы движка."""
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass
            self._engine = None
