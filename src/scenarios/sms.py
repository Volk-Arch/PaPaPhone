# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# https://www.gnu.org/licenses/gpl-3.0.html
"""
Сценарии чтения SMS.

ReadSMSScenario       — все SMS по одному (с пагинацией)
ReadUnreadSMSScenario — только непрочитанные
"""
from src.contacts import db as contacts_db
from src.scenarios.base import BaseScenario, ScenarioContext, CONFIRM_TIMEOUT

_NEXT_WORDS = ("дальше", "следующее", "следующий", "ещё", "еще", "да", "читай")
_CALL_WORDS = ("позвони", "позвонить", "набери", "звонок", "перезвони")
_STOP_WORDS = ("хватит", "всё", "все", "достаточно", "нет")

_SMS_TEXT_LIMIT = 150


def _sender_name(sender: str) -> str:
    """Определить имя отправителя через контакты."""
    if not sender:
        return "неизвестный"
    found = contacts_db.find_by_phone(sender)
    return found[1] if found else sender


def _read_messages(self, ctx: ScenarioContext, messages: list) -> None:
    """Зачитать список SMS по одному с пагинацией."""
    total = len(messages)
    limit = min(total, 10)
    ctx.tts.say(f"{'Одно сообщение' if total == 1 else f'{total} сообщений'}.")

    for i, msg in enumerate(messages[:limit], 1):
        sender = _sender_name(msg.sender)
        text = msg.text[:_SMS_TEXT_LIMIT]
        if len(msg.text) > _SMS_TEXT_LIMIT:
            text += "... обрезано"

        ctx.tts.say(f"От {sender}: {text}")

        # Меню после каждого SMS
        ctx.tts.say("Дальше, позвонить, или хватит?")
        answer = self._listen(ctx, CONFIRM_TIMEOUT)
        if not answer or not answer.strip():
            break

        a = answer.lower().strip()

        # Позвонить отправителю
        if any(w in a for w in _CALL_WORDS):
            if msg.sender:
                from src.scenarios.call import CallNumberScenario
                found = contacts_db.find_by_phone(msg.sender)
                if found:
                    from src.scenarios.call import CallContactScenario
                    CallContactScenario(found[1]).run(ctx)
                else:
                    CallNumberScenario(msg.sender).run(ctx)
            else:
                ctx.tts.say("Номер отправителя неизвестен.")
            break

        if any(w in a for w in _STOP_WORDS):
            break

        if not any(w in a for w in _NEXT_WORDS):
            ctx.tts.say("Не расслышала. Останавливаю.")
            break

    ctx.tts.say("Чтение завершено.")


class ReadSMSScenario(BaseScenario):
    """Все SMS по одному."""

    def run(self, ctx: ScenarioContext) -> None:
        if ctx.mock_modem:
            ctx.tts.say("Демо: сообщений нет.")
            return
        if not ctx.modem_serial:
            ctx.tts.say("Модем не подключён.")
            return

        from src.modem import sms as modem_sms
        messages = modem_sms.list_sms(ctx.modem_serial, folder="ALL")
        if not messages:
            ctx.tts.say("Сообщений нет.")
            return
        _read_messages(self, ctx, messages)


class ReadUnreadSMSScenario(BaseScenario):
    """Только непрочитанные SMS."""

    def run(self, ctx: ScenarioContext) -> None:
        if ctx.mock_modem:
            ctx.tts.say("Демо: непрочитанных нет.")
            return
        if not ctx.modem_serial:
            ctx.tts.say("Модем не подключён.")
            return

        from src.modem import sms as modem_sms
        messages = modem_sms.list_sms(ctx.modem_serial, folder="REC UNREAD")
        if not messages:
            ctx.tts.say("Непрочитанных сообщений нет.")
            return
        _read_messages(self, ctx, messages)
