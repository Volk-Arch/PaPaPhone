# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Абстрактный интерфейс провайдера звонков."""
from abc import ABC, abstractmethod
from typing import Optional


class CallProvider(ABC):
    """Единый интерфейс для звонков — AT-модем или VoIP."""

    @abstractmethod
    def dial(self, number: str) -> bool:
        """Исходящий звонок. Возвращает True если соединение начато."""

    @abstractmethod
    def answer(self) -> bool:
        """Принять входящий звонок."""

    @abstractmethod
    def hangup(self) -> bool:
        """Завершить активный звонок."""

    @abstractmethod
    def get_call_status(self) -> Optional[str]:
        """Статус текущего звонка: 'active', 'ringing', None (нет звонка)."""

    @abstractmethod
    def get_incoming_caller(self) -> Optional[str]:
        """Номер входящего (ringing). None если нет входящего."""

    def shutdown(self) -> None:
        """Освободить ресурсы (переопределить при необходимости)."""


class DemoCallProvider(CallProvider):
    """Заглушка для демо-режима. Звонки симулируются."""

    def dial(self, number: str) -> bool:
        return True

    def answer(self) -> bool:
        return True

    def hangup(self) -> bool:
        return True

    def get_call_status(self) -> Optional[str]:
        return "active"  # в демо звонок "всегда активен" пока не скажут положить

    def get_incoming_caller(self) -> Optional[str]:
        return None
