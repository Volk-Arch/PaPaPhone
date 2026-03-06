"""
SQLite-хранилище контактов: создание схемы, CRUD, поиск по имени и алиасам.
"""
import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from src.config import CONTACTS_DB_PATH, DATA_DIR


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_connection() -> sqlite3.Connection:
    _ensure_data_dir()
    conn = sqlite3.connect(str(CONTACTS_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(schema_path: Optional[Path] = None) -> None:
    """Создать таблицы из schema.sql при первом запуске."""
    if schema_path is None:
        schema_path = Path(__file__).parent / "schema.sql"
    _ensure_data_dir()
    conn = _get_connection()
    try:
        schema = schema_path.read_text(encoding="utf-8")
        conn.executescript(schema)
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


def find_by_name_or_alias(query: str) -> List[Tuple[int, str, str]]:
    """
    Поиск контакта по имени или любому алиасу (без учёта регистра).
    Возвращает список (id, name, phone).
    """
    init_db()
    q = _normalize_for_search(query)
    if not q:
        return []
    conn = _get_connection()
    try:
        cur = conn.execute(
            "SELECT id, name, phone, aliases FROM contacts"
        )
        results: List[Tuple[int, str, str]] = []
        for row in cur:
            name_norm = _normalize_for_search(row["name"])
            if name_norm == q or q in name_norm or name_norm in q:
                results.append((row["id"], row["name"], row["phone"]))
                continue
            try:
                aliases = json.loads(row["aliases"] or "[]")
            except json.JSONDecodeError:
                aliases = []
            for alias in aliases:
                alias_norm = _normalize_for_search(str(alias))
                if alias_norm == q or q in alias_norm or alias_norm in q:
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
