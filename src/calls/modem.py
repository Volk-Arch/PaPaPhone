# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Провайдер звонков через AT-модем SIM7600."""
from typing import Optional

from src.calls.provider import CallProvider
from src.modem.serial_io import ModemSerial


class ModemCallProvider(CallProvider):
    """Звонки через SIM7600 AT-команды."""

    def __init__(self, modem_serial: ModemSerial) -> None:
        self._serial = modem_serial

    def dial(self, number: str) -> bool:
        from src.modem.call import dial
        return dial(self._serial, number)

    def answer(self) -> bool:
        from src.modem.call import answer
        return answer(self._serial)

    def hangup(self) -> bool:
        from src.modem.call import hangup
        return hangup(self._serial)

    def get_call_status(self) -> Optional[str]:
        from src.modem.call import get_call_status
        return get_call_status(self._serial)

    def get_incoming_caller(self) -> Optional[str]:
        from src.modem.call import get_incoming_caller
        return get_incoming_caller(self._serial)
