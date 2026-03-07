# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Сопоставление распознанного текста со словарём команд.
Логика выполнения вынесена в src/scenarios/.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.commands.dictionary import (
    get_phrases_by_action,
    get_slot_for_action,
    load_commands,
)


@dataclass
class MatchedCommand:
    action: str
    slot_value: Optional[str] = None  # имя контакта или цифровой номер


def _normalize(text: str) -> str:
    return text.lower().strip()


def _extract_digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _first_word(s: str) -> str:
    parts = s.split()
    return parts[0] if parts else ""


def _phrase_in_text(phrase: str, text: str) -> bool:
    """
    Проверить что фраза встречается в тексте как целое слово/словосочетание,
    а не как подстрока внутри слова.
    Пример: «позвони» НЕ матчит «позвонить», но матчит «позвони тесту».
    """
    if phrase == text:
        return True
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    return bool(re.search(pattern, text))


def _remove_phrase(phrase: str, text: str) -> str:
    """Удалить первое целословное вхождение фразы из текста."""
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    return re.sub(pattern, "", text, count=1).strip()


def match_command(
    text: str,
    commands: Optional[List[Dict[str, Any]]] = None,
) -> Optional[MatchedCommand]:
    """
    Сопоставить текст с командой из словаря.
    Возвращает MatchedCommand или None.
    """
    if not text or not text.strip():
        return None

    commands = commands or load_commands()
    phrases_by_action = get_phrases_by_action(commands)
    slot_by_action = get_slot_for_action(commands)
    normalized = _normalize(text)

    for action, phrases in phrases_by_action.items():
        for phrase in phrases:
            if _phrase_in_text(phrase, normalized):
                slot_name = slot_by_action.get(action)
                if slot_name == "contact_name":
                    rest = _remove_phrase(phrase, normalized)
                    if rest:
                        return MatchedCommand(action=action, slot_value=_first_word(rest))
                if slot_name == "number":
                    digits = _extract_digits(text)
                    if digits:
                        return MatchedCommand(action=action, slot_value=digits)
                return MatchedCommand(action=action)

    # Fallback: «позвони/набери <имя или номер>»
    for prefix in ("позвони ", "набери ", "позвонить ", "набрать "):
        if normalized.startswith(prefix):
            rest = normalized[len(prefix):].strip()
            if rest and not rest.isdigit():
                return MatchedCommand(action="call_contact", slot_value=_first_word(rest))
            if rest and rest.isdigit():
                return MatchedCommand(action="call_number", slot_value=_extract_digits(text))

    return None
