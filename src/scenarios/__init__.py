# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Маршрутизация распознанного текста -> сценарий.

get_scenario(text) -- единственная публичная функция.
IncomingCallScenario экспортируется для main.py / FSM.
"""
from typing import Optional

from src.commands.executor import MatchedCommand, match_command
from src.scenarios.base import BaseScenario
from src.scenarios.call import (
    AnswerScenario,
    CallContactScenario,
    CallNumberScenario,
    EmergencyScenario,
    HangupScenario,
    IncomingCallScenario,
)
from src.scenarios.contacts import (
    AddContactScenario,
    AliasContactScenario,
    FindContactScenario,
    SecretMenuScenario,
)
from src.scenarios.info import (
    AddressScenario,
    CallLogScenario,
    ClearCallLogScenario,
    HelpScenario,
    ListContactsScenario,
    ListEmergencyScenario,
    SignalScenario,
    VolumeDownScenario,
    VolumeUpScenario,
    WhatTimeScenario,
)
from src.scenarios.sms import ReadSMSScenario, ReadUnreadSMSScenario

__all__ = ["get_scenario", "IncomingCallScenario"]

_SIMPLE: dict[str, type[BaseScenario]] = {
    "emergency":       EmergencyScenario,
    "hangup":          HangupScenario,
    "answer":          AnswerScenario,
    "what_time":       WhatTimeScenario,
    "help":            HelpScenario,
    "read_sms":        ReadSMSScenario,
    "read_unread_sms": ReadUnreadSMSScenario,
    "add_contact":     AddContactScenario,
    "list_contacts":   ListContactsScenario,
    "list_emergency":  ListEmergencyScenario,
    "call_log":        CallLogScenario,
    "signal":          SignalScenario,
    "volume_up":       VolumeUpScenario,
    "volume_down":     VolumeDownScenario,
    "clear_call_log":  ClearCallLogScenario,
    "address":         AddressScenario,
    "secret_menu":     SecretMenuScenario,
}

_WITH_CONTACT: dict[str, type[BaseScenario]] = {
    "call_contact":   CallContactScenario,
    "find_contact":   FindContactScenario,
    "alias_contact":  AliasContactScenario,
}


def get_scenario(text: str) -> Optional[BaseScenario]:
    """Вернуть сценарий для распознанного текста или None."""
    matched: Optional[MatchedCommand] = match_command(text)
    if matched is None:
        return None

    action = matched.action
    slot = matched.slot_value

    if action == "call_number":
        if not slot:
            return None
        return CallNumberScenario(slot)

    if action in _WITH_CONTACT:
        if not slot:
            return None
        return _WITH_CONTACT[action](slot)

    cls = _SIMPLE.get(action)
    return cls() if cls else None
