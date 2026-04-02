# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Сценарии звонков.

EmergencyScenario     — экстренный вызов 112 (укороченное подтверждение)
CallContactScenario   — позвонить контакту из книги
CallNumberScenario    — набрать произвольный номер
HangupScenario        — положить трубку
AnswerScenario        — ответить на входящий (по команде пользователя)
IncomingCallScenario  — входящий звонок, обнаруженный системой через AT+CLCC

Исходящие звонки требуют подтверждения перед выполнением.
После соединения все сценарии ждут окончания звонка через _wait_for_call_end().
"""
import sys

from src.contacts import db as contacts_db
from src.scenarios.base import (
    CANCEL_CONFIRM_S,
    CANCEL_WORDS,
    YES_WORDS,
    BaseScenario,
    CancelledError,
    ScenarioContext,
    is_cancel,
)

# Слова для завершения звонка голосом во время разговора
_HANGUP_WORDS = ("положи", "сброс", "отбой", "завершить", "завершь", "закончи")

# Таймаут одного ASR-кванта внутри ожидания конца звонка
_CALL_POLL_S = 3.0


def _is_cancel_or_hangup(text: str) -> str | None:
    """Определить тип команды завершения.

    Возвращает "cancel", "hangup" или None.
    Cancel-слова имеют приоритет (прерывают сценарий полностью).
    """
    t = text.lower()
    if any(w in t for w in CANCEL_WORDS):
        return "cancel"
    if any(w in t for w in _HANGUP_WORDS):
        return "hangup"
    return None


def _do_hangup(ctx: ScenarioContext) -> None:
    """Повесить трубку (реальную или демо)."""
    if ctx.modem_serial:
        from src.modem import call as modem_call
        modem_call.hangup(ctx.modem_serial)


def _confirm_cancel_call(ctx: ScenarioContext) -> bool:
    """Подтверждение отмены во время звонка. Тишина = НЕ отменять."""
    ctx.tts.say("Завершить звонок? Скажите да.", block=True)
    confirm = ctx.asr.listen(timeout_s=CANCEL_CONFIRM_S)
    return bool(confirm and any(w in confirm.lower() for w in YES_WORDS))


def _wait_for_call_end(ctx: ScenarioContext) -> None:
    """Ждать окончания активного звонка.

    Работает короткими квантами ASR (3 с):
    - «положи трубку» / «отбой» → вешает, выходит нормально.
    - «стоп» / «отмена» → подтверждение → вешает + CancelledError.
    - AT+CLCC пустой / remote_hangup → собеседник завершил.
    """
    ctx.in_call = True
    ctx.remote_hangup.clear()
    try:
        if ctx.mock_modem:
            ctx.tts.say(
                "Идёт демо-звонок. Скажите «положи трубку» или нажмите Enter для сброса."
            )
            while True:
                text = ctx.asr.listen(timeout_s=_CALL_POLL_S)
                if text:
                    action = _is_cancel_or_hangup(text)
                    if action == "cancel" and _confirm_cancel_call(ctx):
                        ctx.tts.say("Звонок завершён.")
                        raise CancelledError()
                    if action == "hangup":
                        ctx.tts.say("Звонок завершён.")
                        return
                if ctx.remote_hangup.is_set():
                    ctx.tts.say("Собеседник завершил звонок.")
                    return
            return

        if not ctx.modem_serial:
            return

        while True:
            text = ctx.asr.listen(timeout_s=_CALL_POLL_S)
            if text:
                action = _is_cancel_or_hangup(text)
                if action == "cancel" and _confirm_cancel_call(ctx):
                    _do_hangup(ctx)
                    ctx.tts.say("Звонок завершён.")
                    raise CancelledError()
                if action == "hangup":
                    _do_hangup(ctx)
                    ctx.tts.say("Звонок завершён.")
                    return

            from src.modem.call import get_call_status
            if get_call_status(ctx.modem_serial) is None:
                ctx.tts.say("Звонок завершён.")
                return
    finally:
        ctx.in_call = False


# Таймаут подтверждения экстренного вызова (короче обычного — 3 с)
_EMERGENCY_CONFIRM_S = 3.0

# Слова отмены экстренного вызова (только явный отказ)
_EMERGENCY_CANCEL = ("нет", "не надо")


class EmergencyScenario(BaseScenario):
    """Экстренный вызов 112.

    - Тишина = ЗВОНИТЬ (если дедушке плохо, он может не ответить)
    - Только явное «нет» отменяет
    - При звонке шлёт SMS всем экстренным контактам из БД
    """

    def _notify_emergency_contacts(self, ctx: ScenarioContext, sos_number: str) -> None:
        """Отправить SMS экстренным контактам."""
        from src.config import HOME_ADDRESS
        emergency = contacts_db.get_emergency_contacts()
        if not emergency or not ctx.modem_serial:
            return
        from src.modem import sms as modem_sms
        text = f"Экстренный вызов! Вызвана помощь по номеру {sos_number}. Адрес: {HOME_ADDRESS}"
        for _id, name, phone in emergency:
            try:
                modem_sms.send_sms(ctx.modem_serial, phone, text)
                print(f"[EMERGENCY] SMS: {name} ({phone})", file=sys.stderr)
            except Exception as e:
                print(f"[EMERGENCY] SMS не отправлено {name}: {e}", file=sys.stderr)

    def run(self, ctx: ScenarioContext) -> None:
        sos_number = contacts_db.get_sos_number()
        spoken = " ".join(sos_number)

        ctx.tts.say(f"Экстренный вызов {spoken}. Для отмены скажите нет.")

        answer = self._listen(ctx, _EMERGENCY_CONFIRM_S)

        if answer and any(w in answer.lower() for w in _EMERGENCY_CANCEL):
            ctx.tts.say("Экстренный вызов отменён.")
            return

        self._notify_emergency_contacts(ctx, sos_number)

        ctx.tts.say(f"Звоню {spoken}.")

        if ctx.modem_serial:
            from src.modem import call as modem_call
            if modem_call.dial(ctx.modem_serial, sos_number):
                _wait_for_call_end(ctx)
            else:
                ctx.tts.say("Не удалось позвонить. Проверьте связь.")
        elif ctx.mock_modem:
            ctx.tts.say(f"Демо: экстренный вызов {spoken}.")
            _wait_for_call_end(ctx)
        else:
            ctx.tts.say("Модем не подключён.")


class CallContactScenario(BaseScenario):
    def __init__(self, contact_name: str) -> None:
        self._name = contact_name

    def run(self, ctx: ScenarioContext) -> None:
        results = contacts_db.find_by_name_or_alias(self._name)
        if not results:
            ctx.tts.say(f"Контакт {self._name} не найден в книге.")
            return

        _, display, phone = results[0]

        if not self._confirm(ctx, f"Контакт {display}. Для звонка скажите да."):
            return

        contacts_db.log_call(phone, "out")
        if ctx.modem_serial:
            from src.modem import call as modem_call
            if modem_call.dial(ctx.modem_serial, phone):
                ctx.tts.say(f"Звоним {display}.")
                _wait_for_call_end(ctx)
            else:
                ctx.tts.say("Не удалось начать звонок. Проверьте связь.")
        elif ctx.mock_modem:
            ctx.tts.say(f"Демо: звоним {display}.")
            _wait_for_call_end(ctx)
        else:
            ctx.tts.say("Модем не подключён.")


class CallNumberScenario(BaseScenario):
    def __init__(self, number: str) -> None:
        self._number = number

    def run(self, ctx: ScenarioContext) -> None:
        spoken = " ".join(self._number)
        if not self._confirm(ctx, f"Набрать номер {spoken}. Скажите да или нет."):
            return

        if ctx.modem_serial:
            from src.modem import call as modem_call
            if modem_call.dial(ctx.modem_serial, self._number):
                ctx.tts.say("Набираю номер.")
                _wait_for_call_end(ctx)
            else:
                ctx.tts.say("Не удалось набрать номер. Проверьте связь.")
        elif ctx.mock_modem:
            ctx.tts.say(f"Демо: набираю {spoken}.")
            _wait_for_call_end(ctx)
        else:
            ctx.tts.say("Модем не подключён.")


class HangupScenario(BaseScenario):
    def run(self, ctx: ScenarioContext) -> None:
        if ctx.modem_serial:
            from src.modem import call as modem_call
            modem_call.hangup(ctx.modem_serial)
        ctx.tts.say("Звонок завершён.")


class AnswerScenario(BaseScenario):
    """Ответить на входящий по команде пользователя (без подтверждения)."""

    def run(self, ctx: ScenarioContext) -> None:
        if ctx.modem_serial:
            from src.modem import call as modem_call
            modem_call.answer(ctx.modem_serial)
            ctx.tts.say("Принимаю звонок.")
            _wait_for_call_end(ctx)
        elif ctx.mock_modem:
            ctx.tts.say("Демо: принимаю звонок.")
            _wait_for_call_end(ctx)
        else:
            ctx.tts.say("Модем не подключён.")


class IncomingCallScenario(BaseScenario):
    """Входящий звонок, обнаруженный системой через AT+CLCC."""

    def __init__(self, number: str) -> None:
        self._number = number

    def run(self, ctx: ScenarioContext) -> None:
        if self._number:
            found = contacts_db.find_by_phone(self._number)
            caller = found[1] if found else self._number
            contacts_db.log_call(self._number, "in")
        else:
            caller = "неизвестный номер"

        if not self._confirm(ctx, f"Входящий звонок от {caller}. Ответить? Да или нет."):
            if ctx.modem_serial:
                from src.modem import call as modem_call
                modem_call.hangup(ctx.modem_serial)
            ctx.tts.say("Звонок отклонён.")
            return

        if ctx.modem_serial:
            from src.modem import call as modem_call
            modem_call.answer(ctx.modem_serial)
            ctx.tts.say("Звонок принят.")
            _wait_for_call_end(ctx)
        elif ctx.mock_modem:
            ctx.tts.say("Демо: звонок принят.")
            _wait_for_call_end(ctx)
        else:
            ctx.tts.say("Модем не подключён.")
