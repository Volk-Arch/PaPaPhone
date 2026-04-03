# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# https://www.gnu.org/licenses/gpl-3.0.html
"""
Низкоуровневая работа с последовательным портом SIM7600.
Отправка AT-команд и чтение ответов.
"""
import re
import threading
import serial
from typing import Optional

from src.config import (
    MODEM_BAUDRATE,
    MODEM_PORT,
    MODEM_TIMEOUT_READ_S,
    MODEM_TIMEOUT_WRITE_S,
)


class SerialIOError(Exception):
    """Ошибка связи с модулем по UART."""


class ModemSerial:
    """Обёртка над pyserial для обмена AT-командами с SIM7600."""

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = MODEM_BAUDRATE,
        timeout_read: float = MODEM_TIMEOUT_READ_S,
        timeout_write: float = MODEM_TIMEOUT_WRITE_S,
    ) -> None:
        self.port = port or MODEM_PORT
        self.baudrate = baudrate
        self.timeout_read = timeout_read
        self.timeout_write = timeout_write
        self._ser: Optional[serial.Serial] = None
        self.lock = threading.Lock()

    def open(self) -> None:
        """Открыть последовательный порт."""
        if self._ser is not None and self._ser.is_open:
            return
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout_read,
                write_timeout=self.timeout_write,
            )
        except serial.SerialException as e:
            raise SerialIOError(f"Не удалось открыть порт {self.port}: {e}") from e

    def close(self) -> None:
        """Закрыть порт."""
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def send_at(self, cmd: str, term: str = "\r\n") -> str:
        """
        Отправить AT-команду и вернуть весь ответ до OK/ERROR или по таймауту.
        Потокобезопасно (self.lock). Бросает SerialIOError при потере порта.
        """
        if self._ser is None or not self._ser.is_open:
            raise SerialIOError("Порт не открыт")
        with self.lock:
            try:
                cmd_line = cmd.strip() + term
                self._ser.write(cmd_line.encode("utf-8"))
                self._ser.flush()
                response: list[str] = []
                while True:
                    line = self._ser.readline()
                    if not line:
                        break
                    try:
                        decoded = line.decode("utf-8", errors="replace").strip()
                    except Exception:
                        decoded = line.decode("latin-1", errors="replace").strip()
                    if not decoded:
                        continue
                    response.append(decoded)
                    if decoded in ("OK", "ERROR"):
                        break
                    if decoded.startswith("+CME ERROR") or decoded.startswith("+CMS ERROR"):
                        break
                return "\n".join(response)
            except serial.SerialException as e:
                self._ser = None
                raise SerialIOError(f"Порт потерян: {e}") from e

    def send_at_and_check(self, cmd: str) -> bool:
        """Отправить команду и вернуть True, если ответ содержит OK."""
        resp = self.send_at(cmd)
        return "OK" in resp and "ERROR" not in resp.split("OK")[0]

    def read_response_until_ok_or_error(self, timeout_s: Optional[float] = None) -> str:
        """
        Читать строки из порта до OK/ERROR (для команд вроде AT+CMGS,
        где ответ приходит с задержкой после отправки текста).
        """
        if self._ser is None or not self._ser.is_open:
            raise SerialIOError("Порт не открыт")
        old_timeout = self._ser.timeout
        if timeout_s is not None:
            self._ser.timeout = timeout_s
        try:
            response: list[str] = []
            while True:
                line = self._ser.readline()
                if not line:
                    break
                try:
                    decoded = line.decode("utf-8", errors="replace").strip()
                except Exception:
                    decoded = line.decode("latin-1", errors="replace").strip()
                if decoded:
                    response.append(decoded)
                if decoded in ("OK", "ERROR"):
                    break
                if "ERROR" in decoded:
                    break
            return "\n".join(response)
        except serial.SerialException as e:
            self._ser = None
            raise SerialIOError(f"Порт потерян: {e}") from e
        finally:
            if self._ser is not None:
                self._ser.timeout = old_timeout

    def __enter__(self) -> "ModemSerial":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()
