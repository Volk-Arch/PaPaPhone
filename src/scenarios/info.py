# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Информационные сценарии (не требуют подтверждения).

WhatTimeScenario     — который час
HelpScenario         — список команд
ListContactsScenario — назвать все контакты
SignalScenario       — уровень сигнала сети
"""
from src.contacts import db as contacts_db
from src.scenarios.base import BaseScenario, ScenarioContext


class WhatTimeScenario(BaseScenario):
    def run(self, ctx: ScenarioContext) -> None:
        from datetime import datetime
        now = datetime.now()
        h, m = now.hour, now.minute
        ctx.tts.say(f"Сейчас {h} часов {m} минут.")


class HelpScenario(BaseScenario):
    def run(self, ctx: ScenarioContext) -> None:
        ctx.tts.say(
            "Доступные команды: "
            "позвони и имя контакта. "
            "Набери и номер телефона. "
            "Положи трубку. "
            "Ответь на звонок. "
            "Прочитай смс. "
            "Список контактов. "
            "Уровень сигнала. "
            "Который час."
        )


class ListContactsScenario(BaseScenario):
    def run(self, ctx: ScenarioContext) -> None:
        contacts = contacts_db.list_all_contacts()
        if not contacts:
            ctx.tts.say("Книга контактов пуста.")
            return
        names = [c[1] for c in contacts[:10]]
        ctx.tts.say("Контакты: " + ", ".join(names) + ".")
        if len(contacts) > 10:
            ctx.tts.say(f"И ещё {len(contacts) - 10} контактов.")


class SignalScenario(BaseScenario):
    def run(self, ctx: ScenarioContext) -> None:
        if ctx.modem_serial:
            from src.modem import at_commands as at
            rssi, _ = at.get_signal_quality(ctx.modem_serial)
            if rssi is None:
                ctx.tts.say("Не удалось получить уровень сигнала.")
            elif rssi == 99:
                ctx.tts.say("Уровень сигнала неизвестен. Нет сети.")
            elif rssi >= 20:
                ctx.tts.say(f"Сигнал хороший: {rssi} из 31.")
            elif rssi >= 10:
                ctx.tts.say(f"Сигнал слабый: {rssi} из 31.")
            else:
                ctx.tts.say(f"Сигнал очень слабый: {rssi} из 31.")
        elif ctx.mock_modem:
            ctx.tts.say("Демо: сигнал хороший, 20 из 31.")
        else:
            ctx.tts.say("Модем не подключён.")
