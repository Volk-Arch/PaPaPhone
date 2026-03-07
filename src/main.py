# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Точка входа PaPaPhone: главный цикл голосового управления.

Архитектура главного цикла:
  - Wake-петля (таймаут 3 с): ждём «телефон» И проверяем входящие звонки
  - Command-петля: однократный listen → get_scenario → run
  - Входящий звонок прерывает wake-петлю и запускает IncomingCallScenario
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    DATA_DIR,
    VOSK_MODEL_PATH,
    WAKE_PHRASES,
)
from src.contacts import db as contacts_db
from src.modem.serial_io import ModemSerial, SerialIOError
from src.scenarios import IncomingCallScenario, get_scenario
from src.scenarios.base import ScenarioContext
from src.voice.asr import ASR, ASRError
from src.voice.tts import TTS

# Таймаут одного кванта слушания в wake-петле.
# Короткий → быстрое обнаружение входящего звонка между listen-вызовами.
_WAKE_LISTEN_S = 3.0


def _is_wake_phrase(text: str) -> bool:
    if not text or not text.strip():
        return False
    t = text.lower().strip()
    return any(phrase == t or phrase in t for phrase in WAKE_PHRASES)


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="PaPaPhone — голосовой телефон")
    parser.add_argument(
        "--no-modem",
        action="store_true",
        help="Не подключаться к модему",
    )
    parser.add_argument(
        "--listen-timeout",
        type=float,
        default=12.0,
        help="Таймаут ожидания команды в секундах (по умолчанию 12)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Демо-режим: без модема и TTS (только текст в консоль)",
    )
    parser.add_argument(
        "--no-wake",
        action="store_true",
        help="Не требовать wake-фразу «телефон» перед командами",
    )
    args = parser.parse_args()

    ensure_data_dir()
    contacts_db.init_db()

    use_demo = args.demo

    # --- TTS ---
    if use_demo:
        class _TextTTS:
            def is_available(self) -> bool: return True
            def say(self, text: str, block: bool = True) -> None:
                if text and text.strip():
                    print(f"[TTS] {text.strip()}", flush=True)
            def stop(self) -> None: pass
            def shutdown(self) -> None: pass
        tts = _TextTTS()
        print("Демо-режим: вывод только в консоль.", file=sys.stderr)
    else:
        tts = TTS()
        if tts.is_available():
            print("TTS: piper включён.", file=sys.stderr)
        else:
            print("TTS: piper недоступен, вывод в консоль [TTS].", file=sys.stderr)

    # --- Модем ---
    modem_serial: ModemSerial | None = None
    if not args.no_modem and not use_demo:
        try:
            modem_serial = ModemSerial()
            modem_serial.open()
            from src.modem import at_commands as at
            if at.init_modem(modem_serial):
                tts.say("Модем подключён.")
            else:
                tts.say("Модем не ответил.")
                modem_serial.close()
                modem_serial = None
        except SerialIOError as e:
            print(f"Модем: {e}", file=sys.stderr)
            modem_serial = None

    # --- ASR ---
    if not VOSK_MODEL_PATH.exists():
        print(f"Модель Vosk не найдена: {VOSK_MODEL_PATH}", file=sys.stderr)
        print("Скачайте с https://alphacephei.com/vosk/models", file=sys.stderr)
        tts.say("Модель распознавания не найдена. Выход.")
        return 1

    try:
        asr = ASR()
        asr.load_model()
    except ASRError as e:
        print(f"ASR: {e}", file=sys.stderr)
        tts.say("Ошибка микрофона. Выход.")
        return 1

    if use_demo:
        tts.say("Демо-режим. Готов к командам.")
    else:
        tts.say("Готов к командам.")

    # --- Контекст сценариев ---
    ctx = ScenarioContext(
        asr=asr,
        tts=tts,
        modem_serial=modem_serial,
        mock_modem=use_demo,
        listen_timeout=args.listen_timeout,
    )

    use_wake = not args.no_wake and bool(WAKE_PHRASES)
    if use_wake:
        print(f"Жду wake-фразу: «{WAKE_PHRASES[0]}».", file=sys.stderr)

    # --- Главный цикл ---
    try:
        while True:
            # ── Wake-петля ─────────────────────────────────────────────────
            if use_wake:
                tts.say("Скажите телефон.", block=True)
                incoming_handled = False
                while True:
                    text = asr.listen(timeout_s=_WAKE_LISTEN_S)

                    # Проверка входящего звонка между квантами слушания
                    if modem_serial and not use_demo:
                        from src.modem.call import get_incoming_caller
                        number = get_incoming_caller(modem_serial)
                        if number is not None:
                            IncomingCallScenario(number).run(ctx)
                            incoming_handled = True
                            break

                    if text and text.strip():
                        print(f"Распознано: {text}", file=sys.stderr)
                        if _is_wake_phrase(text):
                            break

                if incoming_handled:
                    continue  # вернуться в начало main-loop

            # ── Ждём команду ───────────────────────────────────────────────
            tts.say("Слушаю.", block=True)
            text = asr.listen(timeout_s=args.listen_timeout)

            # Если пауза — проверить входящий звонок
            if (not text or not text.strip()) and modem_serial and not use_demo:
                from src.modem.call import get_incoming_caller
                number = get_incoming_caller(modem_serial)
                if number is not None:
                    IncomingCallScenario(number).run(ctx)
                continue

            if not text or not text.strip():
                continue

            print(f"Распознано: {text}", file=sys.stderr)
            scenario = get_scenario(text)
            if scenario:
                scenario.run(ctx)
            else:
                tts.say("Не понял команду. Скажите помощь — подскажу что умею.")

    except KeyboardInterrupt:
        tts.say("До свидания.")
    finally:
        asr.shutdown()
        tts.shutdown()
        if modem_serial is not None:
            modem_serial.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
