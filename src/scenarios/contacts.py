# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Сценарии управления контактами.

AddContactScenario — добавить контакт голосом:
  1. "Назовите имя" → ASR
  2. "Назовите номер" → ASR (берём только цифры)
  3. Подтверждение → запись в БД
"""
import re

from src.contacts import db as contacts_db
from src.scenarios.base import BaseScenario, ScenarioContext


class AddContactScenario(BaseScenario):
    def run(self, ctx: ScenarioContext) -> None:
        # Шаг 1: имя
        ctx.tts.say("Назовите имя контакта.")
        name_raw = ctx.asr.listen(timeout_s=ctx.listen_timeout)
        if not name_raw or not name_raw.strip():
            ctx.tts.say("Имя не распознано. Отменено.")
            return
        name = name_raw.strip()

        # Шаг 2: номер
        ctx.tts.say(f"Имя: {name}. Теперь назовите номер телефона.")
        number_raw = ctx.asr.listen(timeout_s=ctx.listen_timeout)
        if not number_raw or not number_raw.strip():
            ctx.tts.say("Номер не распознан. Отменено.")
            return

        digits = re.sub(r"\D", "", number_raw)
        if len(digits) < 7:
            ctx.tts.say("Номер слишком короткий. Проверьте и попробуйте снова.")
            return

        spoken_digits = " ".join(digits)

        # Шаг 3: подтверждение
        if not self._confirm(
            ctx,
            f"Добавить контакт {name}, номер {spoken_digits}. Да или нет?",
        ):
            return

        contacts_db.add_contact(name, digits)
        ctx.tts.say(f"Контакт {name} добавлен.")
