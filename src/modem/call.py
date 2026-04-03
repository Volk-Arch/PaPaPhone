# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# https://www.gnu.org/licenses/gpl-3.0.html
"""
Управление звонками через SIM7600: исходящие, входящие, сброс.
"""
import re
from typing import Callable, Optional

from src.modem.serial_io import ModemSerial, SerialIOError


def dial(serial_io: ModemSerial, number: str) -> bool:
    """
    Исходящий звонок: ATD<number>;
    number — строка с цифрами и +, запятые для пауз.
    """
    number_clean = re.sub(r"[^\d+]", "", number)
    if not number_clean:
        return False
    cmd = f"ATD{number_clean};"
    resp = serial_io.send_at(cmd)
    return "OK" in resp


def answer(serial_io: ModemSerial) -> bool:
    """Ответ на входящий: ATA."""
    resp = serial_io.send_at("ATA")
    return "OK" in resp


def hangup(serial_io: ModemSerial) -> bool:
    """Завершить звонок: ATH."""
    resp = serial_io.send_at("ATH")
    return "OK" in resp


def get_call_status(serial_io: ModemSerial) -> Optional[str]:
    """
    AT+CLCC — список текущих вызовов.
    Возвращает упрощённый статус: 'active', 'incoming', 'outgoing', None.
    """
    resp = serial_io.send_at("AT+CLCC")
    for line in resp.splitlines():
        if line.strip().startswith("+CLCC:"):
            parts = line.split(":")[1].strip().split(",")
            if len(parts) >= 2:
                try:
                    direction = int(parts[1].strip())
                    status = int(parts[2].strip()) if len(parts) > 2 else 0
                    if direction == 1:
                        return "outgoing"
                    if direction == 2:
                        return "incoming"
                    return "active"
                except (ValueError, IndexError):
                    pass
    return None


def parse_ring_line(line: str) -> Optional[str]:
    """
    Парсинг RING и +CLIP:..." для номера входящего.
    Возвращает номер звонящего или None.
    """
    if "+CLIP:" in line:
        match = re.search(r'\+CLIP:\s*"([^"]*)"', line)
        if match:
            return match.group(1).strip()
    return None


def get_incoming_caller(serial_io: ModemSerial) -> Optional[str]:
    """
    AT+CLCC — проверить, есть ли входящий звонок (dir=1/MT, status=4/ringing).
    Возвращает номер звонящего, '' если номер не определён, None если звонка нет.
    Формат: +CLCC: idx,dir,status,mode,mpty[,number,type[,alpha]]
    """
    try:
        resp = serial_io.send_at("AT+CLCC")
        for line in resp.splitlines():
            line = line.strip()
            if not line.startswith("+CLCC:"):
                continue
            parts = [p.strip().strip('"') for p in line.split(":", 1)[1].split(",")]
            if len(parts) < 3:
                continue
            try:
                direction = int(parts[1])
                status = int(parts[2])
            except ValueError:
                continue
            if direction == 1 and status == 4:  # MT incoming ringing
                return parts[5] if len(parts) > 5 else ""
    except Exception:
        pass
    return None


def wait_for_incoming(
    serial_io: ModemSerial,
    on_ring: Optional[Callable[[], None]] = None,
    on_clip: Optional[Callable[[str], None]] = None,
    timeout_s: float = 1.0,
) -> bool:
    """
    Читать порт в ожидании RING и опционально +CLIP.
    При RING вызывается on_ring(), при +CLIP — on_clip(number).
    Возвращает True, если получен хотя бы один RING.
    """
    if not serial_io.is_open():
        return False
    old_timeout = serial_io._ser.timeout
    serial_io._ser.timeout = timeout_s
    seen_ring = False
    try:
        while True:
            line = serial_io._ser.readline()
            if not line:
                break
            try:
                decoded = line.decode("utf-8", errors="replace").strip()
            except Exception:
                decoded = line.decode("latin-1", errors="replace").strip()
            if decoded == "RING":
                seen_ring = True
                if on_ring:
                    on_ring()
            elif "+CLIP:" in decoded:
                number = parse_ring_line(decoded)
                if number and on_clip:
                    on_clip(number)
    finally:
        serial_io._ser.timeout = old_timeout
    return seen_ring
