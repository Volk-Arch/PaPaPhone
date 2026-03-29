# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""Состояния конечного автомата PaPaPhone."""
from enum import Enum, auto


class State(Enum):
    IDLE = auto()       # Ожидание wake-фразы, опрос входящих
    LISTENING = auto()  # Wake получен, ждём команду
    EXECUTING = auto()  # Сценарий выполняется (blocking)
    IN_CALL = auto()    # Активный звонок (_wait_for_call_end)
    INCOMING = auto()   # Обработка входящего звонка
