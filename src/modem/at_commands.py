# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Базовые AT-команды SIM7600: проверка связи, сеть, уровень сигнала.
"""
from typing import Optional, Tuple

from src.modem.serial_io import ModemSerial, SerialIOError


def check_at(serial_io: ModemSerial) -> bool:
    """Проверка связи: AT -> OK."""
    return serial_io.send_at_and_check("AT")


def get_manufacturer(serial_io: ModemSerial) -> Optional[str]:
    """AT+CGMI — производитель."""
    resp = serial_io.send_at("AT+CGMI")
    for line in resp.splitlines():
        line = line.strip()
        if line and line not in ("AT+CGMI", "OK"):
            return line
    return None


def get_model(serial_io: ModemSerial) -> Optional[str]:
    """AT+CGMM — модель."""
    resp = serial_io.send_at("AT+CGMM")
    for line in resp.splitlines():
        line = line.strip()
        if line and line not in ("AT+CGMM", "OK"):
            return line
    return None


def get_signal_quality(serial_io: ModemSerial) -> Tuple[Optional[int], Optional[int]]:
    """
    AT+CSQ — уровень сигнала.
    Возвращает (rssi, ber). rssi 0-31 (99 — неизвестно), ber 0-7 (99 — неизвестно).
    """
    resp = serial_io.send_at("AT+CSQ")
    for line in resp.splitlines():
        if line.strip().startswith("+CSQ:"):
            part = line.split(":")[1].strip()
            parts = part.split(",")
            try:
                rssi = int(parts[0].strip()) if len(parts) > 0 else None
                ber = int(parts[1].strip()) if len(parts) > 1 else None
                return (rssi, ber)
            except (ValueError, IndexError):
                return (None, None)
    return (None, None)


def get_network_registration(serial_io: ModemSerial) -> Optional[int]:
    """
    AT+CREG? — статус регистрации в сети.
    0 — не зарегистрирован, 1 — зарегистрирован в домашней сети,
    2 — поиск, 3 — отклонено, 4 — неизвестно, 5 — зарегистрирован в роуминге.
    """
    resp = serial_io.send_at("AT+CREG?")
    for line in resp.splitlines():
        if "+CREG:" in line:
            parts = line.split(",")
            if len(parts) >= 2:
                try:
                    return int(parts[1].strip())
                except ValueError:
                    pass
    return None


def get_attach_gprs(serial_io: ModemSerial) -> Optional[int]:
    """AT+CGATT? — присоединение к GPRS (0/1)."""
    resp = serial_io.send_at("AT+CGATT?")
    for line in resp.splitlines():
        if "+CGATT:" in line:
            try:
                return int(line.split(":")[1].strip())
            except (ValueError, IndexError):
                pass
    return None


def init_modem(serial_io: ModemSerial) -> bool:
    """
    Инициализация модема: проверить связь, настроить аудио и звонки.
    Возвращает True, если модуль отвечает.
    """
    try:
        if not check_at(serial_io):
            return False
        # Выключить echo — ответы предсказуемы
        serial_io.send_at("ATE0")
        # Включить определитель номера (CLIP) — нужен для IncomingCallScenario
        serial_io.send_at("AT+CLIP=1")
        # Максимальная громкость звонка (0–5)
        serial_io.send_at("AT+CRSL=5")
        # Максимальная громкость динамика во время разговора (0–5)
        serial_io.send_at("AT+CLVL=5")
        return True
    except SerialIOError:
        return False
