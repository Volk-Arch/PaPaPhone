# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# https://www.gnu.org/licenses/gpl-3.0.html
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
            "Сигнал. "
            "Громче. Тише. "
            "Последние звонки. "
            "Спасите — экстренный вызов. "
            "Стоп — отменить."
        )


class ListContactsScenario(BaseScenario):
    """Зачитать все контакты."""

    def run(self, ctx: ScenarioContext) -> None:
        all_contacts = contacts_db.list_all_contacts()
        if not all_contacts:
            ctx.tts.say("Книга контактов пуста.")
            return
        names = [name for _, name, _ in all_contacts]
        ctx.tts.say(f"Контактов: {len(all_contacts)}. {', '.join(names)}.")


class ListEmergencyScenario(BaseScenario):
    """Зачитать экстренные контакты."""

    def run(self, ctx: ScenarioContext) -> None:
        emergency = contacts_db.get_emergency_contacts()
        if not emergency:
            ctx.tts.say("Экстренных контактов нет.")
            return
        names = [name for _, name, _ in emergency]
        ctx.tts.say(f"Экстренных: {len(emergency)}. {', '.join(names)}.")


class CallLogScenario(BaseScenario):
    """Последние звонки."""

    def run(self, ctx: ScenarioContext) -> None:
        log = contacts_db.get_call_log(limit=5)
        if not log:
            ctx.tts.say("Звонков пока не было.")
            return
        ctx.tts.say(f"Последних звонков: {len(log)}.")
        for phone, direction, ts in log:
            found = contacts_db.find_by_phone(phone)
            name = found[1] if found else f"номер {' '.join(phone)}"
            dir_text = "входящий от" if direction == "in" else "исходящий"
            time_part = ts.split(" ")[1][:5] if " " in ts else ""
            h, m = time_part.split(":") if ":" in time_part else ("", "")
            ctx.tts.say(f"{dir_text} {name}, в {h} {m}.")


class ClearCallLogScenario(BaseScenario):
    """Очистить историю звонков (секретное меню)."""

    def run(self, ctx: ScenarioContext) -> None:
        if self._confirm(ctx, "Очистить историю звонков? Да или нет."):
            contacts_db.clear_call_log()
            ctx.tts.say("История звонков очищена.")


class SignalScenario(BaseScenario):
    """Уровень сигнала сети."""

    def run(self, ctx: ScenarioContext) -> None:
        if ctx.modem_serial:
            from src.modem import at_commands as at
            rssi, _ = at.get_signal_quality(ctx.modem_serial)
            if rssi is None:
                ctx.tts.say("Не удалось получить уровень сигнала.")
            elif rssi == 99:
                ctx.tts.say("Нет сети.")
            elif rssi >= 20:
                ctx.tts.say(f"Сигнал хороший.")
            elif rssi >= 10:
                ctx.tts.say(f"Сигнал слабый.")
            else:
                ctx.tts.say(f"Сигнал очень слабый.")
        elif ctx.mock_modem:
            ctx.tts.say("Демо: сигнал хороший.")
        else:
            ctx.tts.say("Модем не подключён.")


def _get_volume() -> int | None:
    """Получить текущую громкость Master (0-100) через amixer."""
    import re
    import subprocess
    try:
        result = subprocess.run(
            ["amixer", "get", "Master"], capture_output=True, text=True, timeout=5
        )
        m = re.search(r"\[(\d+)%\]", result.stdout)
        return int(m.group(1)) if m else None
    except Exception:
        return None


class VolumeUpScenario(BaseScenario):
    """Увеличить громкость на 10%."""

    def run(self, ctx: ScenarioContext) -> None:
        import subprocess
        vol = _get_volume()
        if vol is not None and vol >= 100:
            ctx.tts.say("Уже максимальная громкость.")
            return
        try:
            subprocess.run(["amixer", "set", "Master", "10%+"], capture_output=True, timeout=5)
            new_vol = _get_volume()
            if new_vol is not None:
                ctx.tts.say(f"Громкость {new_vol} процентов.")
            else:
                ctx.tts.say("Громче.")
        except Exception:
            ctx.tts.say("Не удалось изменить громкость.")


class VolumeDownScenario(BaseScenario):
    """Уменьшить громкость на 10%."""

    def run(self, ctx: ScenarioContext) -> None:
        import subprocess
        vol = _get_volume()
        if vol is not None and vol <= 10:
            ctx.tts.say("Уже минимальная громкость.")
            return
        try:
            subprocess.run(["amixer", "set", "Master", "10%-"], capture_output=True, timeout=5)
            new_vol = _get_volume()
            if new_vol is not None:
                ctx.tts.say(f"Громкость {new_vol} процентов.")
            else:
                ctx.tts.say("Тише.")
        except Exception:
            ctx.tts.say("Не удалось изменить громкость.")


class AddressScenario(BaseScenario):
    """Озвучить домашний адрес."""

    def run(self, ctx: ScenarioContext) -> None:
        ctx.tts.say(f"Ваш адрес: {HOME_ADDRESS}")
