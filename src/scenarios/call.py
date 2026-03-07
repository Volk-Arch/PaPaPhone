# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Сценарии звонков.

CallContactScenario   — позвонить контакту из книги
CallNumberScenario    — набрать произвольный номер
HangupScenario        — положить трубку
AnswerScenario        — ответить на входящий (по команде пользователя)
IncomingCallScenario  — входящий звонок, обнаруженный системой через AT+CLCC

Исходящие звонки требуют подтверждения перед выполнением.
После соединения все сценарии ждут окончания звонка через _wait_for_call_end().
"""
from src.contacts import db as contacts_db
from src.scenarios.base import BaseScenario, ScenarioContext

# Слова для завершения звонка голосом во время разговора
_HANGUP_WORDS = ("положи", "сброс", "отбой", "завершить", "завершь", "стоп", "закончи")

# Таймаут одного ASR-кванта внутри ожидания конца звонка
_CALL_POLL_S = 3.0


def _wait_for_call_end(ctx: ScenarioContext) -> None:
    """
    Ждать окончания активного звонка.

    Работает короткими квантами ASR (3 с):
    - Если пользователь говорит «положи трубку» / «сброс» / «отбой» → вешает сам.
    - Если AT+CLCC пустой (звонок завершился удалённо) → объявляет и выходит.
    В демо-режиме (mock_modem) — симулирует звонок, ждёт голосовой команды завершения.
    """
    if ctx.mock_modem:
        ctx.tts.say("Идёт демо-звонок. Скажите «положи трубку» для завершения.")
        while True:
            text = ctx.asr.listen(timeout_s=_CALL_POLL_S)
            if text and any(w in text.lower() for w in _HANGUP_WORDS):
                ctx.tts.say("Звонок завершён.")
                return
        return

    if not ctx.modem_serial:
        return

    while True:
        text = ctx.asr.listen(timeout_s=_CALL_POLL_S)
        if text and any(w in text.lower() for w in _HANGUP_WORDS):
            from src.modem import call as modem_call
            modem_call.hangup(ctx.modem_serial)
            ctx.tts.say("Звонок завершён.")
            return

        from src.modem.call import get_call_status
        if get_call_status(ctx.modem_serial) is None:
            ctx.tts.say("Звонок завершён.")
            return


class CallContactScenario(BaseScenario):
    def __init__(self, contact_name: str) -> None:
        self._name = contact_name

    def run(self, ctx: ScenarioContext) -> None:
        results = contacts_db.find_by_name_or_alias(self._name)
        if not results:
            ctx.tts.say(f"Контакт {self._name} не найден в книге.")
            return

        _, display, phone = results[0]

        if not self._confirm(ctx, f"Звоню {display}, номер {phone}. Скажите да или нет."):
            return

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
        else:
            ctx.tts.say("Принимаю звонок.")


class IncomingCallScenario(BaseScenario):
    """
    Входящий звонок, обнаруженный системой через AT+CLCC.
    Объявляет кто звонит, спрашивает ответить или сбросить.
    При молчании/таймауте — сбрасывает (безопасный дефолт).
    После ответа ждёт окончания разговора.
    """

    def __init__(self, number: str) -> None:
        self._number = number  # пустая строка если CLIP недоступен

    def run(self, ctx: ScenarioContext) -> None:
        # Определить имя звонящего
        if self._number:
            found = contacts_db.find_by_phone(self._number)
            caller = found[1] if found else self._number
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
