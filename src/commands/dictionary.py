"""
Загрузка словаря команд из YAML.
"""
from pathlib import Path
from typing import Any, Dict, List

import yaml

from src.config import COMMANDS_YAML_PATH


def load_commands(path: Path | None = None) -> List[Dict[str, Any]]:
    """
    Загрузить data/commands.yaml и вернуть список записей команд.
    Каждая запись: action, phrases (list), опционально slot, description.
    """
    p = path or COMMANDS_YAML_PATH
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return data


def get_phrases_by_action(commands: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Словарь action -> список фраз (в нижнем регистре)."""
    result: Dict[str, List[str]] = {}
    for cmd in commands:
        action = cmd.get("action")
        if not action:
            continue
        phrases = cmd.get("phrases") or []
        result[action] = [p.strip().lower() for p in phrases if p]
    return result


def get_slot_for_action(commands: List[Dict[str, Any]]) -> Dict[str, str]:
    """Словарь action -> имя слота (contact_name, number и т.д.)."""
    result: Dict[str, str] = {}
    for cmd in commands:
        action = cmd.get("action")
        slot = cmd.get("slot")
        if action and slot:
            result[action] = str(slot).strip()
    return result
