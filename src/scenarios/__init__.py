# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Маршрутизация распознанного текста → сценарий.

get_scenario(text) — единственная публичная функция.
Возвращает экземпляр сценария или None, если текст не распознан.
IncomingCallScenario экспортируется для использования в main.py.
"""
from typing import Optional

from src.commands.executor import MatchedCommand, match_command
from src.scenarios.base import BaseScenario
from src.scenarios.call import (
    AnswerScenario,
    CallContactScenario,
    CallNumberScenario,
    HangupScenario,
    IncomingCallScenario,
)
from src.scenarios.contacts import AddContactScenario
from src.scenarios.info import (
    HelpScenario,
    ListContactsScenario,
    SignalScenario,
    WhatTimeScenario,
)
from src.scenarios.sms import ReadSMSScenario

__all__ = ["get_scenario", "IncomingCallScenario"]

# Сценарии без слота (action → класс)
_SIMPLE: dict[str, type[BaseScenario]] = {
    "hangup":        HangupScenario,
    "answer":        AnswerScenario,
    "what_time":     WhatTimeScenario,
    "help":          HelpScenario,
    "signal":        SignalScenario,
    "list_contacts": ListContactsScenario,
    "read_sms":      ReadSMSScenario,
    "add_contact":   AddContactScenario,
}


def get_scenario(text: str) -> Optional[BaseScenario]:
    """Вернуть сценарий для распознанного текста или None."""
    matched: Optional[MatchedCommand] = match_command(text)
    if matched is None:
        return None

    action = matched.action
    slot = matched.slot_value

    if action == "call_contact":
        if not slot:
            return None  # имя не распознано
        return CallContactScenario(slot)

    if action == "call_number":
        if not slot:
            return None
        return CallNumberScenario(slot)

    cls = _SIMPLE.get(action)
    return cls() if cls else None
