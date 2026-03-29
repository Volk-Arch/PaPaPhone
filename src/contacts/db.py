# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
SQLite-хранилище контактов: создание схемы, CRUD, поиск по имени и алиасам.

Поиск использует морфологическую нормализацию (pymorphy3), чтобы склонения
имён распознавались корректно: «позвони Оле» → найдёт «Оля».
"""
import json
import re
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from src.config import CONTACTS_DB_PATH, DATA_DIR

# ---------------------------------------------------------------------------
# Морфологический анализатор (pymorphy3). Graceful fallback если не установлен.
# ---------------------------------------------------------------------------
try:
    import pymorphy3 as _pymorphy3
    _morph = _pymorphy3.MorphAnalyzer()

    def _to_normal_forms(word: str) -> set:
        """Все возможные нормальные формы слова (именительный падеж, ед. число).

        pymorphy3 может дать несколько вариантов разбора с одинаковым score,
        например «ане» → {«ана», «аня»}. Для поиска контактов важно проверить все.
        """
        if not word:
            return {word}
        return {p.normal_form for p in _morph.parse(word)}

except ImportError:  # pragma: no cover
    def _to_normal_forms(word: str) -> set:  # type: ignore[misc]
        """Заглушка: pymorphy3 не установлен."""
        return {word.lower()}


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_connection() -> sqlite3.Connection:
    _ensure_data_dir()
    conn = sqlite3.connect(str(CONTACTS_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(schema_path: Optional[Path] = None) -> None:
    """Создать таблицы из schema.sql + миграция is_emergency."""
    if schema_path is None:
        schema_path = Path(__file__).parent / "schema.sql"
    _ensure_data_dir()
    conn = _get_connection()
    try:
        schema = schema_path.read_text(encoding="utf-8")
        conn.executescript(schema)
        # Миграция: добавить is_emergency если старая БД без неё
        try:
            conn.execute("SELECT is_emergency FROM contacts LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE contacts ADD COLUMN is_emergency INTEGER DEFAULT 0")
        conn.commit()
    finally:
        conn.close()


def add_contact(name: str, phone: str, aliases: Optional[List[str]] = None) -> int:
    """
    Добавить контакт. aliases — варианты произношения для голосового поиска.
    Возвращает id вставленной строки.
    """
    init_db()
    aliases_json = json.dumps(aliases or [], ensure_ascii=False)
    conn = _get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO contacts (name, phone, aliases) VALUES (?, ?, ?)",
            (name.strip(), phone.strip(), aliases_json),
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def _normalize_for_search(s: str) -> str:
    return s.lower().strip()


def _matches(stored: str, query_raw: str, query_norms: set) -> bool:
    """
    Проверить совпадение строки `stored` с запросом:
    1. Сырое сравнение (подстрока): «оле» in «оля» — близкое написание.
    2. Морфологическое: пересечение нормальных форм stored и query.
       «ане» → {ана, аня}, «Аня» → {аня} — пересечение {аня} → совпадение.
    """
    s = _normalize_for_search(stored)
    if s == query_raw or query_raw in s or s in query_raw:
        return True
    s_norms = _to_normal_forms(s)
    return bool(s_norms & query_norms)


def find_by_name_or_alias(query: str) -> List[Tuple[int, str, str]]:
    """
    Поиск контакта по имени или любому алиасу (без учёта регистра).
    Поддерживает склонения: «Оле» найдёт «Оля», «маме» найдёт «мама».
    Возвращает список (id, name, phone).
    """
    init_db()
    q_raw = _normalize_for_search(query)
    if not q_raw:
        return []
    q_norms = _to_normal_forms(q_raw)  # все нормальные формы запроса

    conn = _get_connection()
    try:
        cur = conn.execute(
            "SELECT id, name, phone, aliases FROM contacts"
        )
        results: List[Tuple[int, str, str]] = []
        for row in cur:
            if _matches(row["name"], q_raw, q_norms):
                results.append((row["id"], row["name"], row["phone"]))
                continue
            try:
                aliases = json.loads(row["aliases"] or "[]")
            except json.JSONDecodeError:
                aliases = []
            for alias in aliases:
                if _matches(str(alias), q_raw, q_norms):
                    results.append((row["id"], row["name"], row["phone"]))
                    break
        return results
    finally:
        conn.close()


def get_phone_by_name(name_or_alias: str) -> Optional[str]:
    """
    Получить номер телефона по имени или алиасу (первое совпадение).
    """
    found = find_by_name_or_alias(name_or_alias)
    return found[0][2] if found else None


def find_by_phone(number: str) -> Optional[Tuple[int, str, str]]:
    """
    Найти контакт по номеру телефона (первое совпадение).
    Сравнение по последним 7 цифрам — не зависит от формата кода страны.
    Возвращает (id, name, phone) или None.
    """
    if not number:
        return None
    digits = re.sub(r"\D", "", number)
    tail = digits[-7:] if len(digits) >= 7 else digits
    if not tail:
        return None
    init_db()
    conn = _get_connection()
    try:
        cur = conn.execute("SELECT id, name, phone FROM contacts")
        for row in cur:
            row_digits = re.sub(r"\D", "", row["phone"] or "")
            if row_digits.endswith(tail):
                return (row["id"], row["name"], row["phone"])
        return None
    finally:
        conn.close()


def list_all_contacts() -> List[Tuple[int, str, str]]:
    """Список всех контактов: (id, name, phone)."""
    init_db()
    conn = _get_connection()
    try:
        cur = conn.execute("SELECT id, name, phone FROM contacts ORDER BY name")
        return [(r["id"], r["name"], r["phone"]) for r in cur]
    finally:
        conn.close()


def update_contact(
    contact_id: int,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    aliases: Optional[List[str]] = None,
) -> bool:
    """Обновить контакт по id."""
    init_db()
    conn = _get_connection()
    try:
        if name is not None:
            conn.execute("UPDATE contacts SET name = ? WHERE id = ?", (name, contact_id))
        if phone is not None:
            conn.execute("UPDATE contacts SET phone = ? WHERE id = ?", (phone, contact_id))
        if aliases is not None:
            conn.execute(
                "UPDATE contacts SET aliases = ? WHERE id = ?",
                (json.dumps(aliases, ensure_ascii=False), contact_id),
            )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def delete_contact(contact_id: int) -> bool:
    """Удалить контакт по id."""
    init_db()
    conn = _get_connection()
    try:
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def set_emergency(contact_id: int, is_emergency: bool) -> bool:
    """Пометить/снять пометку экстренного контакта."""
    init_db()
    conn = _get_connection()
    try:
        conn.execute(
            "UPDATE contacts SET is_emergency = ? WHERE id = ?",
            (1 if is_emergency else 0, contact_id),
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def get_emergency_contacts() -> List[Tuple[int, str, str]]:
    """Все экстренные контакты: (id, name, phone)."""
    init_db()
    conn = _get_connection()
    try:
        cur = conn.execute(
            "SELECT id, name, phone FROM contacts WHERE is_emergency = 1 ORDER BY name"
        )
        return [(r["id"], r["name"], r["phone"]) for r in cur]
    finally:
        conn.close()
