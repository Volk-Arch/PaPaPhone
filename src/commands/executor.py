# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Сопоставление распознанного текста со словарём команд.

Стратегия извлечения имени контакта:
1. Находим фразу команды в тексте, убираем её
2. Из остатка пробуем каждое слово через contacts DB (морфология)
3. Первый матч из БД = слот (display name)
4. Нет матча в БД = первое не-шумовое слово (fallback)
"""
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from src.commands.dictionary import (
    get_phrases_by_action,
    get_slot_for_action,
    load_commands,
)

# Гарантированный мусор: никогда не имя контакта.
_NOISE = frozenset({
    "а", "в", "и", "к", "о", "с", "у",
    "ну", "же", "ка", "вот", "вон", "эй", "ой", "ах", "ох",
    "пожалуйста", "просто", "давай", "давайте", "ладно",
    "можешь", "может", "слушай", "скажи", "короче", "вообще",
    "мне", "мой", "моя", "моё", "мои", "моему", "моей", "моего",
    "это", "то", "там", "тут", "ещё", "еще",
})


@dataclass
class MatchedCommand:
    action: str
    slot_value: Optional[str] = None


def _build_command_words(commands: List[Dict[str, Any]]) -> Set[str]:
    words = set()
    for cmd in commands:
        for phrase in cmd.get("phrases") or []:
            for w in phrase.lower().split():
                words.add(w)
    return words


def _normalize(text: str) -> str:
    return text.lower().strip()


def _extract_digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _first_word(s: str) -> str:
    parts = s.split()
    return parts[0] if parts else ""


def _phrase_in_text(phrase: str, text: str) -> bool:
    if phrase == text:
        return True
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    return bool(re.search(pattern, text))


def _remove_phrase(phrase: str, text: str) -> str:
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    return re.sub(pattern, "", text, count=1).strip()


def _resolve_contact_name(text: str, cmd_words: Set[str]) -> Optional[str]:
    """Найти имя контакта в тексте.

    1. Пробуем каждое слово через БД контактов (морфология: "маме" → "Мама")
    2. Если в БД не нашли — берём первое не-шумовое, не-командное слово
    """
    from src.contacts import db as contacts_db

    words = text.split()

    # Сначала ищем в БД — каждое слово
    for w in words:
        if w in cmd_words or w in _NOISE:
            continue
        results = contacts_db.find_by_name_or_alias(w)
        if results:
            # Нашли в БД — возвращаем display name
            display = results[0][1]
            print(f"[CMD] Контакт из БД: «{w}» → {display}", file=sys.stderr)
            return display

    # Fallback: первое незнакомое слово (контакт может быть ещё не в БД)
    for w in words:
        if w not in cmd_words and w not in _NOISE:
            print(f"[CMD] Контакт fallback: «{w}»", file=sys.stderr)
            return w

    return None


def match_command(
    text: str,
    commands: Optional[List[Dict[str, Any]]] = None,
) -> Optional[MatchedCommand]:
    """Сопоставить текст с командой из словаря."""
    if not text or not text.strip():
        return None

    commands = commands or load_commands()
    phrases_by_action = get_phrases_by_action(commands)
    slot_by_action = get_slot_for_action(commands)
    cmd_words = _build_command_words(commands)

    normalized = _normalize(text)
    print(f"[CMD] «{normalized}»", file=sys.stderr)

    for action, phrases in phrases_by_action.items():
        for phrase in phrases:
            if _phrase_in_text(phrase, normalized):
                slot_name = slot_by_action.get(action)
                if slot_name == "contact_name":
                    rest = _remove_phrase(phrase, normalized)
                    name = _resolve_contact_name(rest, cmd_words)
                    if name:
                        return MatchedCommand(action=action, slot_value=name)
                if slot_name == "number":
                    digits = _extract_digits(text)
                    if digits:
                        return MatchedCommand(action=action, slot_value=digits)
                return MatchedCommand(action=action)

    return None
