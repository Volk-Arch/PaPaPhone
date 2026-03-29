# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Информационные сценарии.

WhatTimeScenario — который час
HelpScenario     — список функций
AddressScenario  — озвучить домашний адрес
"""
from src.config import HOME_ADDRESS
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
            "Вот что я умею. "
            "Позвони и имя. "
            "Набери номер. "
            "Найди и имя. "
            "Добавь контакт. "
            "Список контактов. "
            "Ответь. "
            "Положи трубку. "
            "Сообщения. "
            "Новые сообщения. "
            "Который час. "
            "Адрес. "
            "Спасите — экстренный вызов. "
            "Стоп — отменить."
        )


class ListContactsScenario(BaseScenario):
    """Зачитать все контакты с пометкой экстренных."""

    def run(self, ctx: ScenarioContext) -> None:
        all_contacts = contacts_db.list_all_contacts()
        if not all_contacts:
            ctx.tts.say("Книга контактов пуста.")
            return
        emergency = {c[0] for c in contacts_db.get_emergency_contacts()}
        names = []
        for cid, name, _ in all_contacts:
            label = f"{name}, экстренный" if cid in emergency else name
            names.append(label)
        ctx.tts.say(f"Контактов: {len(all_contacts)}. {', '.join(names)}.")


class AddressScenario(BaseScenario):
    """Озвучить домашний адрес."""

    def run(self, ctx: ScenarioContext) -> None:
        ctx.tts.say(f"Ваш адрес: {HOME_ADDRESS}")
