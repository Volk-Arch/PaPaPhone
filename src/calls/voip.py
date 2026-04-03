# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Провайдер звонков через VoIP (SIP).

Использует pyVoIP для регистрации на SIP-сервере (Zadarma, Sipnet и т.д.)
и управления звонками. Аудио через ALSA Orange Pi.
"""
import sys
import threading
from typing import Optional

from src.calls.provider import CallProvider

try:
    from pyVoIP.VoIP import VoIPPhone, CallState, PhoneStatus
    _HAS_PYVOIP = True
except ImportError:
    _HAS_PYVOIP = False


class VoipCallProvider(CallProvider):
    """SIP-звонки через pyVoIP."""

    def __init__(
        self,
        sip_server: str,
        sip_user: str,
        sip_password: str,
        sip_port: int = 5060,
    ) -> None:
        if not _HAS_PYVOIP:
            raise ImportError("pyVoIP не установлен: pip install pyVoIP")

        self._server = sip_server
        self._user = sip_user
        self._password = sip_password
        self._port = sip_port

        self._phone: Optional[VoIPPhone] = None
        self._current_call = None
        self._incoming_number: Optional[str] = None
        self._lock = threading.Lock()

        self._start_phone()

    def _start_phone(self) -> None:
        """Зарегистрироваться на SIP-сервере."""
        try:
            self._phone = VoIPPhone(
                self._server,
                self._port,
                self._user,
                self._password,
                callCallback=self._on_incoming,
            )
            self._phone.start()
            print(f"[VOIP] Зарегистрирован: {self._user}@{self._server}", file=sys.stderr)
        except Exception as e:
            print(f"[VOIP] Ошибка регистрации: {e}", file=sys.stderr)
            self._phone = None

    def _on_incoming(self, call) -> None:
        """Callback при входящем звонке от pyVoIP."""
        with self._lock:
            try:
                # Извлекаем номер звонящего из SIP URI
                request = call.request
                from_header = str(request.headers.get("From", ""))
                # Парсим SIP URI: "Name" <sip:number@server>
                number = self._parse_sip_number(from_header)
                self._incoming_number = number or ""
                self._current_call = call
                print(f"[VOIP] Входящий от {number}", file=sys.stderr)
            except Exception as e:
                print(f"[VOIP] Ошибка входящего: {e}", file=sys.stderr)

    @staticmethod
    def _parse_sip_number(from_header: str) -> Optional[str]:
        """Извлечь номер из SIP From header."""
        import re
        # sip:+79001234567@server или sip:12345@server
        m = re.search(r"sip:([^@>]+)@", from_header)
        return m.group(1) if m else None

    def dial(self, number: str) -> bool:
        if not self._phone:
            return False
        try:
            call = self._phone.call(number)
            with self._lock:
                self._current_call = call
            print(f"[VOIP] Звоним: {number}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[VOIP] Ошибка набора: {e}", file=sys.stderr)
            return False

    def answer(self) -> bool:
        with self._lock:
            call = self._current_call
        if not call:
            return False
        try:
            call.answer()
            print("[VOIP] Звонок принят.", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[VOIP] Ошибка ответа: {e}", file=sys.stderr)
            return False

    def hangup(self) -> bool:
        with self._lock:
            call = self._current_call
            self._current_call = None
            self._incoming_number = None
        if not call:
            return True
        try:
            call.hangup()
            print("[VOIP] Звонок завершён.", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[VOIP] Ошибка завершения: {e}", file=sys.stderr)
            return False

    def get_call_status(self) -> Optional[str]:
        with self._lock:
            call = self._current_call
        if not call:
            return None
        try:
            state = call.state
            if state == CallState.ANSWERED:
                return "active"
            if state == CallState.RINGING:
                return "ringing"
            # Звонок завершён
            with self._lock:
                self._current_call = None
            return None
        except Exception:
            return None

    def get_incoming_caller(self) -> Optional[str]:
        with self._lock:
            call = self._current_call
            number = self._incoming_number
        if not call:
            return None
        try:
            if call.state == CallState.RINGING:
                return number
        except Exception:
            pass
        return None

    def shutdown(self) -> None:
        if self._phone:
            try:
                self._phone.stop()
                print("[VOIP] Остановлен.", file=sys.stderr)
            except Exception:
                pass
            self._phone = None
