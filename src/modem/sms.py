# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
SMS через SIM7600: режим текста, отправка, чтение списка.
"""
import re
import time
from dataclasses import dataclass
from typing import List, Optional

from src.modem.serial_io import ModemSerial, SerialIOError


@dataclass
class SmsMessage:
    index: int
    sender: str
    text: str
    timestamp: Optional[str] = None
    read: bool = True


def set_text_mode(serial_io: ModemSerial) -> bool:
    """AT+CMGF=1 — режим текстовых SMS."""
    return serial_io.send_at_and_check("AT+CMGF=1")


def send_sms(serial_io: ModemSerial, number: str, text: str) -> bool:
    """
    Отправить SMS: AT+CMGS="<number>" затем текст и Ctrl+Z (0x1A).
    """
    if not set_text_mode(serial_io):
        return False
    number_clean = number.strip().strip('"')
    cmd = f'AT+CMGS="{number_clean}"'
    serial_io._ser.write((cmd + "\r\n").encode("utf-8"))
    serial_io._ser.flush()
    time.sleep(0.2)
    serial_io._ser.write((text + "\x1A").encode("utf-8"))
    serial_io._ser.flush()
    resp = serial_io.read_response_until_ok_or_error(timeout_s=15.0)
    return "OK" in resp


def list_sms(serial_io: ModemSerial, folder: str = "ALL") -> List[SmsMessage]:
    """
    AT+CMGL="ALL" / "REC UNREAD" / "REC READ" и т.д.
    Парсинг ответа в список SmsMessage.
    """
    if not set_text_mode(serial_io):
        return []
    cmd = f'AT+CMGL="{folder}"'
    resp = serial_io.send_at(cmd)
    messages: List[SmsMessage] = []
    lines = resp.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("+CMGL:"):
            try:
                part = line.split(":", 1)[1].strip()
                parts = [p.strip().strip('"') for p in part.split(",")]
                idx = int(parts[0])
                status = parts[1] if len(parts) > 1 else ""
                sender = parts[2] if len(parts) > 2 else ""
                ts = parts[4] if len(parts) > 4 else None
                i += 1
                text_lines = []
                while i < len(lines) and not lines[i].strip().startswith("+CMGL:") and lines[i].strip() not in ("OK", "ERROR"):
                    text_lines.append(lines[i])
                    i += 1
                text = "\n".join(text_lines).strip()
                messages.append(
                    SmsMessage(
                        index=idx,
                        sender=sender,
                        text=text,
                        timestamp=ts,
                        read=status.upper() in ("REC READ", "STO SENT"),
                    )
                )
            except (ValueError, IndexError):
                i += 1
        else:
            i += 1
    return messages


def read_sms(serial_io: ModemSerial, index: int) -> Optional[SmsMessage]:
    """AT+CMGR=<index> — прочитать одно сообщение по индексу."""
    if not set_text_mode(serial_io):
        return None
    resp = serial_io.send_at(f"AT+CMGR={index}")
    lines = resp.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("+CMGR:"):
            try:
                part = line.split(":", 1)[1].strip()
                parts = [p.strip().strip('"') for p in part.split(",")]
                idx = int(parts[0])
                status = parts[1] if len(parts) > 1 else ""
                sender = parts[2] if len(parts) > 2 else ""
                ts = parts[4] if len(parts) > 4 else None
                text_lines = lines[i + 1 :]
                text = "\n".join(l for l in text_lines if l.strip() not in ("OK", "ERROR")).strip()
                return SmsMessage(
                    index=idx,
                    sender=sender,
                    text=text,
                    timestamp=ts,
                    read=status.upper() in ("REC READ", "STO SENT"),
                )
            except (ValueError, IndexError):
                pass
    return None


def delete_sms(serial_io: ModemSerial, index: int) -> bool:
    """AT+CMGD=<index> — удалить сообщение."""
    return serial_io.send_at_and_check(f"AT+CMGD={index}")
