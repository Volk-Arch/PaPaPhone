# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# https://www.gnu.org/licenses/gpl-3.0.html
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


_FUZZY_CONTACT_THRESHOLD = 70  # порог Левенштейна для контактов


def _resolve_contact_name(text: str, cmd_words: Set[str]) -> Optional[str]:
    """Найти имя контакта в тексте.

    1. Точный матч через БД (морфология: "маме" → "Мама")
    2. Fuzzy-матч: rapidfuzz по всем именам/алиасам из БД
    3. Fallback: первое не-шумовое слово (контакт может быть не в БД)
    """
    from src.contacts import db as contacts_db

    words = [w for w in text.split() if w not in cmd_words and w not in _NOISE]
    if not words:
        return None

    # Фаза 1: точный матч (морфология)
    for w in words:
        results = contacts_db.find_by_name_or_alias(w)
        if results:
            display = results[0][1]
            print(f"[CMD] Контакт из БД: «{w}» → {display}", file=sys.stderr)
            return display

    # Фаза 2: fuzzy по именам и алиасам
    try:
        from rapidfuzz import fuzz
        import json

        all_contacts = contacts_db.list_all_contacts()
        best_score = 0.0
        best_display = None

        for _id, name, phone in all_contacts:
            # Сравниваем каждое слово текста с именем и алиасами
            candidates = [name.lower()]
            # Морфологические формы имени (игорь → игорю, игоря, игорем...)
            try:
                import pymorphy3
                morph = pymorphy3.MorphAnalyzer()
                parsed = morph.parse(name.lower())
                if parsed:
                    for form in parsed[0].lexeme:
                        candidates.append(form.word)
            except ImportError:
                pass
            # Алиасы из БД
            conn = contacts_db._get_connection()
            try:
                row = conn.execute(
                    "SELECT aliases FROM contacts WHERE id = ?", (_id,)
                ).fetchone()
                if row and row["aliases"]:
                    try:
                        aliases = json.loads(row["aliases"])
                        candidates.extend(a.lower() for a in aliases if a)
                    except (json.JSONDecodeError, TypeError):
                        pass
            finally:
                conn.close()

            for w in words:
                for candidate in candidates:
                    score = fuzz.ratio(w, candidate)
                    if score > best_score:
                        best_score = score
                        best_display = name

        if best_score >= _FUZZY_CONTACT_THRESHOLD and best_display:
            print(
                f"[CMD] Контакт fuzzy: «{' '.join(words)}» → {best_display} (score={best_score:.0f})",
                file=sys.stderr,
            )
            return best_display
    except ImportError:
        pass  # rapidfuzz не установлен

    # Фаза 3: fallback — сырое слово
    if words:
        print(f"[CMD] Контакт fallback: «{words[0]}»", file=sys.stderr)
        return words[0]

    return None


# Глобальный FuzzyMatcher — инициализируется лениво при первом вызове
_fuzzy_matcher = None


def _get_fuzzy(commands: List[Dict[str, Any]]):
    global _fuzzy_matcher
    if _fuzzy_matcher is None:
        try:
            from src.commands.fuzzy import FuzzyMatcher
            _fuzzy_matcher = FuzzyMatcher(commands)
        except ImportError:
            _fuzzy_matcher = False  # rapidfuzz не установлен
    return _fuzzy_matcher if _fuzzy_matcher is not False else None


def match_command(
    text: str,
    commands: Optional[List[Dict[str, Any]]] = None,
) -> Optional[MatchedCommand]:
    """Сопоставить текст с командой из словаря.

    Фаза 1: Точный матч по фразам.
    Фаза 2: Fuzzy (Левенштейн + эмбеддинги) если точный не нашёл.
    """
    if not text or not text.strip():
        return None

    commands = commands or load_commands()
    phrases_by_action = get_phrases_by_action(commands)
    slot_by_action = get_slot_for_action(commands)
    cmd_words = _build_command_words(commands)

    normalized = _normalize(text)
    print(f"[CMD] «{normalized}»", file=sys.stderr)

    # Фаза 1: точный матч
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

    # Фаза 2: fuzzy fallback
    fuzzy = _get_fuzzy(commands)
    if fuzzy:
        fm = fuzzy.match(normalized)
        if fm:
            action = fm.action
            slot_name = slot_by_action.get(action)
            if slot_name == "contact_name":
                name = _resolve_contact_name(normalized, cmd_words)
                if name:
                    return MatchedCommand(action=action, slot_value=name)
            if slot_name == "number":
                digits = _extract_digits(text)
                if digits:
                    return MatchedCommand(action=action, slot_value=digits)
            return MatchedCommand(action=action)

    return None
