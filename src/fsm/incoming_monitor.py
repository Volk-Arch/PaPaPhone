# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Фоновый мониторинг входящих звонков через AT+CLCC.

Работает в daemon-потоке, опрашивает модем с заданным интервалом.
Использует ModemSerial.lock для потокобезопасного доступа к serial.
"""
import sys
import threading
from typing import Optional

from src.modem.call import get_incoming_caller
from src.modem.serial_io import ModemSerial

_DEFAULT_POLL_S = 2.0


class IncomingCallMonitor:

    def __init__(
        self,
        modem_serial: ModemSerial,
        poll_interval: float = _DEFAULT_POLL_S,
    ):
        self._serial = modem_serial
        self._interval = poll_interval
        self._stop_event = threading.Event()
        self._enabled = threading.Event()
        self._enabled.set()
        self._incoming_caller: Optional[str] = None
        self._data_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="incoming-monitor"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def disable(self) -> None:
        self._enabled.clear()

    def enable(self) -> None:
        self._enabled.set()

    def check_incoming(self) -> Optional[str]:
        with self._data_lock:
            caller = self._incoming_caller
            self._incoming_caller = None
        return caller

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self._interval):
                break
            if not self._enabled.is_set():
                continue
            # send_at уже потокобезопасен (ModemSerial.lock)
            try:
                caller = get_incoming_caller(self._serial)
                if caller is not None:
                    with self._data_lock:
                        self._incoming_caller = caller
            except Exception as e:
                print(f"[CALL-MON] {e}", file=sys.stderr)
