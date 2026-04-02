# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Конечный автомат PaPaPhone.

Заменяет while-True цикл в main.py.
Состояния и переходы описаны в src/fsm/states.py.
"""
import sys
from typing import List, Optional, Tuple

from src.fsm.states import State
from src.scenarios import IncomingCallScenario, get_scenario
from src.scenarios.base import CancelledError, ScenarioContext

# Таймаут одного кванта слушания в IDLE (короткий → быстрое обнаружение входящего)
_IDLE_LISTEN_S = 3.0


def parse_wake_and_command(
    text: str, wake_phrases: List[str]
) -> Tuple[bool, str]:
    """
    Проверить наличие wake-фразы в тексте и вернуть остаток.

    Возвращает (wake_found, remainder).
    Пример: "телефон позвони сыну" → (True, "позвони сыну")
             "позвони сыну"        → (False, "позвони сыну")
             "телефон"              → (True, "")
    """
    t = text.lower().strip()
    # Пробуем длинные фразы первыми, чтобы "папафон" не съел часть "папафон позвони"
    for phrase in sorted(wake_phrases, key=len, reverse=True):
        idx = t.find(phrase)
        if idx != -1:
            before = t[:idx]
            after = t[idx + len(phrase):]
            # Склеиваем и нормализуем пробелы
            remainder = " ".join((before + " " + after).split())
            return True, remainder
    return False, t


class PhoneFSM:
    """Конечный автомат голосового управления."""

    def __init__(
        self,
        ctx: ScenarioContext,
        incoming_monitor=None,  # Optional[IncomingCallMonitor]
        sms_monitor=None,      # Optional[SmsMonitor]
        use_wake: bool = True,
        wake_phrases: List[str] = None,
    ):
        self._ctx = ctx
        self._monitor = incoming_monitor
        self._sms_monitor = sms_monitor
        self._use_wake = use_wake
        self._wake_phrases = wake_phrases or []
        self._state = State.IDLE
        self._first_idle = True
        self._sms_announced = False

    @property
    def state(self) -> State:
        return self._state

    def run(self) -> None:
        """Главный цикл автомата. Вызывается из main.py."""
        if self._monitor:
            self._monitor.start()
        if self._sms_monitor:
            self._sms_monitor.start()
        try:
            while True:
                try:
                    if self._state == State.IDLE:
                        self._handle_idle()
                    elif self._state == State.LISTENING:
                        self._handle_listening()
                except CancelledError:
                    # Отмена вне сценария — просто вернуться в IDLE
                    self._state = State.IDLE
                    self._first_idle = True
                except KeyboardInterrupt:
                    raise  # пробрасываем наверх
                except Exception as e:
                    # Любая ошибка — логируем, сбрасываем в IDLE, продолжаем
                    print(f"[FSM] ОШИБКА: {type(e).__name__}: {e}", file=sys.stderr)
                    self._ctx.in_call = False
                    self._state = State.IDLE
                    self._first_idle = True
                    try:
                        self._ctx.tts.say("Произошла ошибка. Попробуйте снова.")
                    except Exception:
                        pass  # TTS тоже может быть мёртв
        except KeyboardInterrupt:
            self._ctx.tts.say("До свидания.")
        finally:
            if self._monitor:
                self._monitor.stop()
            if self._sms_monitor:
                self._sms_monitor.stop()

    # ── Обработчики состояний ──────────────────────────────────────────

    def _handle_idle(self) -> None:
        """IDLE: слушаем wake-фразу (или команду если --no-wake)."""
        if self._first_idle:
            if self._use_wake:
                self._ctx.tts.say("Скажите телефон.", block=True)
            self._first_idle = False

        text = self._ctx.asr.listen(timeout_s=_IDLE_LISTEN_S)

        # Проверяем входящий звонок и SMS между квантами слушания
        if self._check_incoming():
            return
        self._check_sms()

        if not text or not text.strip():
            return  # тишина — остаёмся в IDLE

        print(f"[FSM:IDLE] Распознано: {text}", file=sys.stderr)

        if not self._use_wake:
            # Без wake — сразу команда
            self._dispatch_command(text)
            return

        wake_found, remainder = parse_wake_and_command(text, self._wake_phrases)
        if not wake_found:
            return  # нет wake-фразы — игнорируем

        if remainder:
            # Wake + команда в одной фразе
            print(f"[FSM] Wake+команда: «{remainder}»", file=sys.stderr)
            self._dispatch_command(remainder)
        else:
            # Только wake — переходим к слушанию команды
            self._state = State.LISTENING
            self._ctx.tts.say("Слушаю.", block=True)

    def _handle_listening(self) -> None:
        """LISTENING: ждём команду после wake-фразы."""
        text = self._ctx.asr.listen(timeout_s=self._ctx.listen_timeout)

        # Проверяем входящий между listen-ами
        if self._check_incoming():
            return

        if not text or not text.strip():
            # Тишина / таймаут — обратно в IDLE
            self._state = State.IDLE
            self._first_idle = True
            return

        print(f"[FSM:LISTENING] Распознано: {text}", file=sys.stderr)
        self._dispatch_command(text)

    # ── Вспомогательные методы ─────────────────────────────────────────

    def _dispatch_command(self, text: str) -> None:
        """Сопоставить текст с командой и запустить сценарий."""
        scenario = get_scenario(text)
        if scenario:
            self._state = State.EXECUTING
            print(f"[FSM] → EXECUTING: {scenario.__class__.__name__}", file=sys.stderr)
            try:
                scenario.run(self._ctx)
            except CancelledError:
                print("[FSM] Отмена сценария.", file=sys.stderr)
                self._ctx.tts.say("Отменено. Слушаю.")
        else:
            self._ctx.tts.say("Не понял команду. Скажите помощь — подскажу что умею.")
        # После выполнения — обратно в IDLE
        self._state = State.IDLE
        self._first_idle = True

    def _check_incoming(self) -> bool:
        """Проверить входящий звонок через монитор. Возвращает True если обработан."""
        if not self._monitor:
            return False
        caller = self._monitor.check_incoming()
        if caller is None:
            return False

        prev_state = self._state
        self._state = State.INCOMING
        self._monitor.disable()
        print(f"[FSM] → INCOMING от {caller}", file=sys.stderr)

        try:
            IncomingCallScenario(caller).run(self._ctx)
        except CancelledError:
            print("[FSM] Отмена входящего.", file=sys.stderr)
            self._ctx.tts.say("Отменено.")

        self._monitor.enable()
        self._state = State.IDLE
        self._first_idle = True
        return True

    def _check_sms(self) -> None:
        """Уведомить о новых SMS.

        Днём: озвучивает каждое SMS сразу.
        Утром (после ночи): говорит только количество.
        Дедушка сам скажет "новые сообщения" чтобы прослушать.
        """
        if not self._sms_monitor:
            return

        pending = self._sms_monitor.pending_count()

        # Утреннее уведомление о накопленных за ночь
        if pending > 0 and not self._sms_announced:
            self._sms_announced = True
            self._ctx.tts.say(
                f"У вас {pending} {'непрочитанное сообщение' if pending == 1 else 'непрочитанных сообщений'}. "
                "Скажите «новые сообщения» чтобы прослушать."
            )
            return

        sms = self._sms_monitor.check_new_sms()
        if sms is None:
            return

        from src.contacts import db as contacts_db
        found = contacts_db.find_by_phone(sms.sender) if sms.sender else None
        sender_name = found[1] if found else sms.sender or "неизвестный"

        text = sms.text[:150]
        if len(sms.text) > 150:
            text += "... обрезано"

        print(f"[FSM] SMS от {sender_name}", file=sys.stderr)
        self._ctx.tts.say(f"Сообщение от {sender_name}. {text}")
