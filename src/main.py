# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# https://www.gnu.org/licenses/gpl-3.0.html
"""
Точка входа PaPaPhone: инициализация и запуск конечного автомата.

Режимы:
  python -m src.main             — продакшн (VoIP + SIM7600 SMS)
  python -m src.main --demo      — отладка без модема и VoIP
  python -m src.main --no-wake   — без wake-фразы
"""
import argparse
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    CALL_MODE,
    DATA_DIR,
    SIP_PASSWORD,
    SIP_PORT,
    SIP_SERVER,
    SIP_USER,
    VOSK_MODEL_PATH,
    WAKE_PHRASES,
)
from src.contacts import db as contacts_db
from src.fsm.engine import PhoneFSM
from src.fsm.incoming_monitor import IncomingCallMonitor
from src.fsm.sms_monitor import SmsMonitor
from src.modem.serial_io import ModemSerial, SerialIOError
from src.scenarios.base import ScenarioContext
from src.voice.asr import ASR, ASRError
from src.voice.tts import TTS


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="PaPaPhone — голосовой телефон")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Отладка без модема и VoIP (Vosk + TTS с fallback)",
    )
    parser.add_argument(
        "--no-wake",
        action="store_true",
        help="Не требовать wake-фразу «телефон» перед командами",
    )
    parser.add_argument(
        "--listen-timeout",
        type=float,
        default=12.0,
        help="Таймаут ожидания команды в секундах (по умолчанию 12)",
    )
    args = parser.parse_args()

    ensure_data_dir()
    contacts_db.init_db()

    is_demo = args.demo

    # --- TTS ---
    tts = TTS()
    if tts.is_available():
        print("TTS: piper включён.", file=sys.stderr)
    else:
        print("TTS: piper недоступен, вывод в консоль [TTS].", file=sys.stderr)

    # --- Модем (для SMS + сигнал, не для звонков) ---
    modem_serial: ModemSerial | None = None
    if not is_demo:
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
    else:
        print("Демо-режим: модем отключён.", file=sys.stderr)

    # --- Провайдер звонков ---
    call_provider = None
    if is_demo:
        from src.calls.provider import DemoCallProvider
        call_provider = DemoCallProvider()
        print("Звонки: демо.", file=sys.stderr)
    elif CALL_MODE == "voip":
        if SIP_SERVER and SIP_USER:
            try:
                from src.calls.voip import VoipCallProvider
                call_provider = VoipCallProvider(SIP_SERVER, SIP_USER, SIP_PASSWORD, SIP_PORT)
                tts.say("VoIP подключён.")
            except Exception as e:
                print(f"VoIP: {e}", file=sys.stderr)
                tts.say("Не удалось подключить VoIP.")
        else:
            print("VoIP: SIP-настройки не заданы в .env", file=sys.stderr)
            tts.say("VoIP не настроен.")
    elif CALL_MODE == "modem" and modem_serial:
        from src.calls.modem import ModemCallProvider
        call_provider = ModemCallProvider(modem_serial)
        print("Звонки: AT-модем.", file=sys.stderr)

    if call_provider is None and not is_demo:
        from src.calls.provider import DemoCallProvider
        call_provider = DemoCallProvider()
        print("Звонки: fallback на демо (провайдер не подключён).", file=sys.stderr)

    # --- ASR ---
    if not VOSK_MODEL_PATH.exists():
        print(f"Модель Vosk не найдена: {VOSK_MODEL_PATH}", file=sys.stderr)
        tts.say("Модель распознавания не найдена. Выход.")
        return 1

    tts.say("Загружаю модель распознавания. Подождите.")
    try:
        asr = ASR()
        asr.load_model()
    except ASRError as e:
        print(f"ASR: {e}", file=sys.stderr)
        tts.say("Ошибка микрофона. Выход.")
        return 1

    tts.say("Телефон готов.")

    # --- Контекст сценариев ---
    ctx = ScenarioContext(
        asr=asr,
        tts=tts,
        call_provider=call_provider,
        modem_serial=modem_serial,  # для SMS
        mock_modem=is_demo,
        listen_timeout=args.listen_timeout,
    )

    use_wake = not args.no_wake and bool(WAKE_PHRASES)

    # --- Мониторы ---
    monitor = IncomingCallMonitor(call_provider) if not is_demo else None
    sms_mon = SmsMonitor(modem_serial) if modem_serial else None

    # --- Конечный автомат ---
    fsm = PhoneFSM(
        ctx=ctx,
        incoming_monitor=monitor,
        sms_monitor=sms_mon,
        use_wake=use_wake,
        wake_phrases=WAKE_PHRASES,
    )

    # --- Демо: Enter = собеседник повесил трубку ---
    if is_demo:
        def _demo_keyboard_listener():
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if ctx.in_call:
                    ctx.remote_hangup.set()
                    print("[DEMO] Симуляция: собеседник повесил трубку.", file=sys.stderr)

        kb_thread = threading.Thread(
            target=_demo_keyboard_listener, daemon=True, name="demo-keyboard"
        )
        kb_thread.start()

    mode = "демо" if is_demo else f"продакшн ({CALL_MODE})"
    wake_info = f"wake «{WAKE_PHRASES[0]}»" if use_wake else "без wake"
    print(f"FSM: {mode}, {wake_info}.", file=sys.stderr)
    if is_demo:
        print("Enter во время звонка = сброс собеседником.", file=sys.stderr)

    try:
        fsm.run()
    finally:
        asr.shutdown()
        tts.shutdown()
        if call_provider:
            call_provider.shutdown()
        if modem_serial is not None:
            modem_serial.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
