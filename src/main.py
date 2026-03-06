"""
Точка входа PaPaPhone: главный цикл голосового управления.
Ожидание голосовой команды → Vosk → сопоставление со словарём → выполнение → TTS-ответ.
Модем подключается при наличии порта; без модема доступны команды контактов, время, помощь.
"""
import argparse
import sys
from pathlib import Path

# Добавить корень проекта в путь для импортов при запуске из любой папки
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.commands.executor import execute_command, match_command
from src.config import (
    COMMANDS_YAML_PATH,
    CONTACTS_DB_PATH,
    DATA_DIR,
    VOSK_MODEL_PATH,
    WAKE_PHRASES,
)
from src.contacts import db as contacts_db
from src.modem.serial_io import ModemSerial, SerialIOError
from src.voice.asr import ASR, ASRError
from src.voice.tts import TTS


def _is_wake_phrase(text: str) -> bool:
    """Проверка: распознанный текст — команда-активатор (телефон, папафон и т.д.)."""
    if not text or not text.strip():
        return False
    t = text.lower().strip()
    for phrase in WAKE_PHRASES:
        if phrase == t or phrase in t:
            return True
    return False


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _run_test_asr(listen_timeout: float, say_response: bool = False) -> int:
    """Режим --test-asr: распознавание речи, вывод в консоль; опционально озвучка ответа (TTS)."""
    if not VOSK_MODEL_PATH.exists():
        print(
            f"Модель Vosk не найдена: {VOSK_MODEL_PATH}",
            file=sys.stderr,
        )
        print(
            "Скачайте с https://alphacephei.com/vosk/models и распакуйте в models/",
            file=sys.stderr,
        )
        return 1
    try:
        asr = ASR()
        asr.load_model()
    except ASRError as e:
        print(f"ASR: {e}", file=sys.stderr)
        return 1
    tts = TTS() if say_response else None
    if say_response:
        print("Режим теста Vosk + TTS. Говорите — текст выведется и будет озвучен. Выход: Ctrl+C.", file=sys.stderr)
    else:
        print("Режим теста Vosk. Говорите в микрофон — текст будет выводиться сюда. Выход: Ctrl+C.", file=sys.stderr)
    try:
        while True:
            print("[ слушаю ... ]", flush=True)
            text = asr.listen(timeout_s=listen_timeout)
            if text and text.strip():
                print(f"Распознано: {text}", flush=True)
                if tts:
                    tts.say(f"Вы сказали: {text}", block=True)
            else:
                print("(тишина или не распознано)", flush=True)
                if tts:
                    tts.say("Не расслышала.", block=True)
    except KeyboardInterrupt:
        print("\nВыход.", file=sys.stderr)
    finally:
        asr.shutdown()
        if tts:
            tts.shutdown()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PaPaPhone — голосовой телефон")
    parser.add_argument(
        "--no-modem",
        action="store_true",
        help="Не подключаться к модему (только контакты, время, помощь)",
    )
    parser.add_argument(
        "--no-asr",
        action="store_true",
        help="Не загружать Vosk (для теста без микрофона)",
    )
    parser.add_argument(
        "--listen-timeout",
        type=float,
        default=12.0,
        help="Таймаут ожидания фразы в секундах (по умолчанию 12)",
    )
    parser.add_argument(
        "--test-asr",
        action="store_true",
        help="Режим теста Vosk: только распознавание, вывод в консоль, без модема и TTS",
    )
    parser.add_argument(
        "--test-asr-say",
        action="store_true",
        help="В режиме --test-asr ещё и озвучивать распознанную фразу (проверка TTS)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Демо-режим: без модема, с имитацией звонков/SMS/сигнала — проверить весь цикл (Vosk + команды + TTS)",
    )
    parser.add_argument(
        "--no-wake",
        action="store_true",
        help="Не требовать команду «телефон» перед основными командами (всегда слушать команды)",
    )
    args = parser.parse_args()

    ensure_data_dir()
    contacts_db.init_db()

    # Режим теста ASR: только Vosk, печать в консоль, без модема и TTS
    if args.test_asr:
        return _run_test_asr(args.listen_timeout, say_response=args.test_asr_say)

    # Демо: полный цикл без модема, с имитацией ответов модема
    use_demo = args.demo

    tts = TTS()
    if tts.is_available():
        print("TTS: озвучка включена.", file=sys.stderr)
    else:
        print("TTS: озвучка недоступна, ответы выводятся в консоль [TTS].", file=sys.stderr)
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

    if use_demo:
        print("Демо-режим: модем не подключён, ответы имитируются.", file=sys.stderr)

    asr: ASR | None = None
    if not args.no_asr:
        if not VOSK_MODEL_PATH.exists():
            print(
                f"Модель Vosk не найдена: {VOSK_MODEL_PATH}",
                file=sys.stderr,
            )
            print(
                "Скачайте с https://alphacephei.com/vosk/models и распакуйте в models/",
                file=sys.stderr,
            )
            tts.say("Модель распознавания речи не найдена.")
        else:
            try:
                asr = ASR()
                asr.load_model()
                if use_demo:
                    tts.say("Демо-режим. Готов к командам.")
                else:
                    tts.say("Готов к командам.")
            except ASRError as e:
                print(f"ASR: {e}", file=sys.stderr)
                asr = None

    if asr is None:
        tts.say("Распознавание речи отключено. Выход.")
        return 1

    use_wake = not args.no_wake and WAKE_PHRASES
    if use_wake:
        wake_hint = WAKE_PHRASES[0]
        print(f"Ожидаю команду-активатор: «{wake_hint}». Затем говорите основную команду.", file=sys.stderr)

    try:
        while True:
            if use_wake:
                # Сначала ждём «телефон» (или другую фразу из WAKE_PHRASES)
                tts.say("Скажите телефон для команд.", block=True)
                while True:
                    text = asr.listen(timeout_s=args.listen_timeout)
                    if not text or not text.strip():
                        continue
                    print(f"Распознано: {text}", file=sys.stderr)
                    if _is_wake_phrase(text):
                        break
                tts.say("Слушаю.", block=True)
            else:
                tts.say("Слушаю.", block=True)

            text = asr.listen(timeout_s=args.listen_timeout)
            if not text or not text.strip():
                continue
            print(f"Распознано: {text}", file=sys.stderr)
            matched = match_command(text)
            if matched:
                resp = execute_command(
                    matched,
                    modem_serial=modem_serial,
                    mock_modem=use_demo,
                    tts_say=tts.say,
                )
                if resp and not tts.is_available():
                    print(f"[Ответ] {resp}", flush=True)
            else:
                tts.say("Не понял команду. Скажите помощь — подскажу команды.")
    except KeyboardInterrupt:
        tts.say("До свидания.")
    finally:
        if asr is not None:
            asr.shutdown()
        tts.shutdown()
        if modem_serial is not None:
            modem_serial.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
