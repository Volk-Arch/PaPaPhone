# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# https://www.gnu.org/licenses/gpl-3.0.html
"""
Базовый класс сценария и контекст выполнения.
Сценарий — полный детерминированный диалог: TTS-подсказка → ASR-ответ → действие.
"""
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

# Слова подтверждения (проверяются через вхождение в распознанную строку)
YES_WORDS = ("да", "давай", "конечно", "ладно", "хорошо", "подтверждаю", "верно")

# Глобальные слова отмены — прерывают ЛЮБОЙ сценарий в ЛЮБОЙ момент
CANCEL_WORDS = ("отмена", "отменить", "остановить", "стоп", "отмени", "хватит")

CONFIRM_TIMEOUT = 8.0   # секунды ожидания ответа на подтверждение
CANCEL_CONFIRM_S = 5.0  # секунды на подтверждение отмены (побольше, чтобы дед успел)


class CancelledError(Exception):
    """Пользователь подтвердил отмену. Сценарий прерван."""


@dataclass
class ScenarioContext:
    asr: Any              # src.voice.asr.ASR
    tts: Any              # src.voice.tts.TTS
    call_provider: Any    # src.calls.provider.CallProvider
    modem_serial: Any     # src.modem.serial_io.ModemSerial или None (для SMS)
    mock_modem: bool
    listen_timeout: float = 12.0
    in_call: bool = False
    remote_hangup: threading.Event = field(default_factory=threading.Event)


def is_cancel(text: str) -> bool:
    """Проверить содержит ли текст слово отмены."""
    if not text:
        return False
    t = text.lower()
    return any(w in t for w in CANCEL_WORDS)


def listen_or_cancel(ctx: ScenarioContext, timeout_s: float) -> Optional[str]:
    """Обёртка над ctx.asr.listen() с проверкой глобальной отмены.

    При cancel-слове — короткое подтверждение (5с).
    «да» = CancelledError. Тишина/«нет» = продолжить (возвращает None).
    """
    text = ctx.asr.listen(timeout_s=timeout_s)
    if text:
        print(f"[ASR] «{text}»", file=sys.stderr)
    if is_cancel(text):
        print("[CANCEL] Обнаружено слово отмены, подтверждаю...", file=sys.stderr)
        ctx.tts.say("Отменить? Скажите да.", block=True)
        confirm = ctx.asr.listen(timeout_s=CANCEL_CONFIRM_S)
        if confirm:
            print(f"[CANCEL] Ответ: «{confirm}»", file=sys.stderr)
        if confirm and any(w in confirm.lower() for w in YES_WORDS):
            raise CancelledError()
        ctx.tts.say("Продолжаем.")
        return None
    return text


class BaseScenario:
    """Базовый сценарий. Каждый подкласс реализует run()."""

    def run(self, ctx: ScenarioContext) -> None:
        raise NotImplementedError

    def _listen(self, ctx: ScenarioContext, timeout_s: float) -> Optional[str]:
        """Слушать с проверкой глобальной отмены."""
        return listen_or_cancel(ctx, timeout_s)

    def _confirm(self, ctx: ScenarioContext, prompt: str) -> bool:
        """
        Озвучить prompt, дождаться да/нет.
        Возвращает True только при явном «да». Молчание или неразборчивость → отмена.
        Бросает CancelledError при подтверждённом слове отмены.
        """
        ctx.tts.say(prompt)
        answer = self._listen(ctx, CONFIRM_TIMEOUT)
        if not answer or not answer.strip():
            ctx.tts.say("Не расслышала. Отменено.")
            return False
        a = answer.lower().strip()
        if any(w in a for w in YES_WORDS):
            return True
        ctx.tts.say("Отменено.")
        return False
