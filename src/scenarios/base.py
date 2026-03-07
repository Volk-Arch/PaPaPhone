# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Базовый класс сценария и контекст выполнения.
Сценарий — полный детерминированный диалог: TTS-подсказка → ASR-ответ → действие.
"""
from dataclasses import dataclass, field
from typing import Any

# Слова подтверждения / отмены (проверяются через вхождение в распознанную строку)
_YES_WORDS = ("да", "давай", "конечно", "ладно", "хорошо", "подтверждаю", "верно")
_NO_WORDS  = ("нет", "не надо", "отмена", "отменить", "отмени", "стоп", "не")

CONFIRM_TIMEOUT = 8.0  # секунды ожидания ответа на подтверждение


@dataclass
class ScenarioContext:
    asr: Any           # src.voice.asr.ASR
    tts: Any           # src.voice.tts.TTS или _TextTTS
    modem_serial: Any  # src.modem.serial_io.ModemSerial или None
    mock_modem: bool
    listen_timeout: float = 12.0


class BaseScenario:
    """Базовый сценарий. Каждый подкласс реализует run()."""

    def run(self, ctx: ScenarioContext) -> None:
        raise NotImplementedError

    def _confirm(self, ctx: ScenarioContext, prompt: str) -> bool:
        """
        Озвучить prompt, дождаться да/нет.
        Возвращает True только при явном «да». Молчание или неразборчивость → отмена.
        """
        ctx.tts.say(prompt)
        answer = ctx.asr.listen(timeout_s=CONFIRM_TIMEOUT)
        if not answer or not answer.strip():
            ctx.tts.say("Не расслышала. Отменено.")
            return False
        a = answer.lower().strip()
        if any(w in a for w in _YES_WORDS):
            return True
        ctx.tts.say("Отменено.")
        return False
