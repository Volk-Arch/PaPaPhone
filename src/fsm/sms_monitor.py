# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# https://www.gnu.org/licenses/gpl-3.0.html
"""
Фоновый мониторинг входящих SMS через AT+CMGL="REC UNREAD".

Опрашивает модем с заданным интервалом. Новые SMS складываются в очередь.
FSM забирает через check_new_sms() и озвучивает когда IDLE.
Если телефон занят (звонок) или ночь — SMS копятся в очереди
и озвучиваются когда станет доступно.
"""
import sys
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from src.modem.serial_io import ModemSerial

_DEFAULT_POLL_S = 15.0

# Ночные часы: SMS копятся, утром уведомление о количестве.
# Настраивается в data/.env: PAPAPHONE_NIGHT_START, PAPAPHONE_NIGHT_END
import os
_NIGHT_START = int(os.environ.get("PAPAPHONE_NIGHT_START", "23"))
_NIGHT_END = int(os.environ.get("PAPAPHONE_NIGHT_END", "9"))


@dataclass
class IncomingSms:
    sender: str
    text: str
    index: int


def _is_night() -> bool:
    h = datetime.now().hour
    return h >= _NIGHT_START or h < _NIGHT_END


class SmsMonitor:
    """Опрос модема на непрочитанные SMS в фоновом потоке с очередью."""

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
        self._queue: deque[IncomingSms] = deque()
        self._seen_indices: set[int] = set()  # чтобы не дублировать
        self._data_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="sms-monitor"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def disable(self) -> None:
        """Отключить (во время звонка). SMS копятся в очереди."""
        self._enabled.clear()

    def enable(self) -> None:
        self._enabled.set()

    def check_new_sms(self) -> Optional[IncomingSms]:
        """Забрать одно SMS из очереди (FIFO). None если пусто.

        Ночью возвращает None — SMS копятся до утра.
        """
        if _is_night():
            return None
        with self._data_lock:
            if self._queue:
                return self._queue.popleft()
        return None

    def pending_count(self) -> int:
        """Сколько SMS в очереди (для утреннего приветствия)."""
        with self._data_lock:
            return len(self._queue)

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self._interval):
                break
            if not self._enabled.is_set():
                continue
            # send_at уже потокобезопасен (ModemSerial.lock)
            try:
                self._check_unread()
            except Exception as e:
                print(f"[SMS-MON] {e}", file=sys.stderr)

    def _check_unread(self) -> None:
        from src.modem.sms import list_sms
        messages = list_sms(self._serial, folder="REC UNREAD")
        if not messages:
            return
        with self._data_lock:
            for msg in messages:
                if msg.index not in self._seen_indices:
                    self._seen_indices.add(msg.index)
                    self._queue.append(IncomingSms(
                        sender=msg.sender,
                        text=msg.text,
                        index=msg.index,
                    ))
                    print(f"[SMS-MON] Новое SMS #{msg.index} от {msg.sender}", file=sys.stderr)
