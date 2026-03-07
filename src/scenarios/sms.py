# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Сценарий чтения SMS.

Читает сообщения по одному; после каждого спрашивает «дальше» или «стоп».
В демо-режиме сообщает, что новых сообщений нет.
"""
from src.scenarios.base import BaseScenario, ScenarioContext, CONFIRM_TIMEOUT

_NEXT_WORDS = ("дальше", "следующее", "следующий", "ещё", "еще", "да", "читай")
_STOP_WORDS = ("стоп", "хватит", "всё", "все", "достаточно", "нет", "хватит")

# Максимум символов текста одного SMS для зачитывания (длинные — обрезаем)
_SMS_TEXT_LIMIT = 150


class ReadSMSScenario(BaseScenario):
    def run(self, ctx: ScenarioContext) -> None:
        if ctx.mock_modem:
            ctx.tts.say("Демо: новых сообщений нет.")
            return

        if not ctx.modem_serial:
            ctx.tts.say("Модем не подключён.")
            return

        from src.modem import sms as modem_sms
        messages = modem_sms.list_sms(ctx.modem_serial, folder="ALL")

        if not messages:
            ctx.tts.say("Новых сообщений нет.")
            return

        total = len(messages)
        ctx.tts.say(f"Есть {total} {'сообщение' if total == 1 else 'сообщений'}.")

        for i, msg in enumerate(messages[:10], 1):
            text = msg.text[:_SMS_TEXT_LIMIT]
            if len(msg.text) > _SMS_TEXT_LIMIT:
                text += "... сообщение обрезано."
            ctx.tts.say(f"Сообщение {i} из {min(total, 10)}, от {msg.sender}: {text}")

            if i < min(total, 10):
                ctx.tts.say("Читать следующее? Скажите дальше или стоп.")
                answer = ctx.asr.listen(timeout_s=CONFIRM_TIMEOUT)
                if not answer or not answer.strip():
                    break
                a = answer.lower().strip()
                if any(w in a for w in _STOP_WORDS):
                    break
                if not any(w in a for w in _NEXT_WORDS):
                    # Не поняли — на всякий случай останавливаемся
                    ctx.tts.say("Не расслышала. Останавливаю чтение.")
                    break

        ctx.tts.say("Чтение завершено.")
