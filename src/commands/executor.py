"""
Сопоставление распознанного текста со словарём команд и выполнение действий.
"""
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from src.commands.dictionary import (
    get_phrases_by_action,
    get_slot_for_action,
    load_commands,
)
from src.contacts import db as contacts_db


@dataclass
class MatchedCommand:
    action: str
    slot_value: Optional[str] = None  # извлечённое имя контакта или номер


def _normalize_text(text: str) -> str:
    return text.lower().strip()


def _extract_digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _first_word(s: str) -> str:
    """Первое слово строки — чтобы отсечь шум Vosk в конце фразы."""
    parts = s.split()
    return parts[0] if parts else ""


def match_command(text: str, commands: Optional[List[Dict[str, Any]]] = None) -> Optional[MatchedCommand]:
    """
    Сопоставить текст пользователя с одной из команд.
    Возвращает MatchedCommand с action и опционально slot_value (имя/номер),
    или None если совпадений нет.
    """
    if not text or not text.strip():
        return None
    commands = commands or load_commands()
    phrases_by_action = get_phrases_by_action(commands)
    slot_by_action = get_slot_for_action(commands)
    normalized = _normalize_text(text)

    for action, phrases in phrases_by_action.items():
        for phrase in phrases:
            if phrase == normalized:
                return MatchedCommand(action=action)
            if phrase in normalized:
                slot_name = slot_by_action.get(action)
                if slot_name == "contact_name":
                    rest = normalized.replace(phrase, "").strip()
                    if rest:
                        return MatchedCommand(action=action, slot_value=_first_word(rest))
                if slot_name == "number":
                    digits = _extract_digits(text)
                    if digits:
                        return MatchedCommand(action=action, slot_value=digits)
                return MatchedCommand(action=action)

    # Попробовать «позвони <имя>» / «набери <имя>» — брать только первое слово как имя (шум Vosk отсекается)
    for prefix in ("позвони ", "набери ", "позвонить ", "набрать "):
        if normalized.startswith(prefix):
            rest = normalized[len(prefix) :].strip()
            if rest and not rest.isdigit():
                return MatchedCommand(action="call_contact", slot_value=_first_word(rest))
            if rest and rest.isdigit():
                return MatchedCommand(action="call_number", slot_value=_extract_digits(text))

    return None


def execute_command(
    matched: MatchedCommand,
    *,
    modem_serial=None,
    mock_modem: bool = False,
    tts_say: Optional[Callable[[str], None]] = None,
    contacts_db_path=None,
) -> str:
    """
    Выполнить команду и вернуть текстовый ответ для озвучки (или пустую строку).
    modem_serial — экземпляр ModemSerial (для звонков/SMS);
    mock_modem — если True и модема нет, имитировать успех (демо-режим);
    tts_say — функция озвучки (вызывается внутри при необходимости).
    """
    say = tts_say or (lambda _: None)
    response = ""
    use_mock = mock_modem and modem_serial is None

    if matched.action == "call_contact":
        name = matched.slot_value
        if not name:
            response = "Скажите, кому позвонить."
            say(response)
            return response
        phone = contacts_db.get_phone_by_name(name)
        if not phone:
            response = f"Контакт {name} не найден."
            say(response)
            return response
        if modem_serial:
            from src.modem import call as modem_call
            if modem_call.dial(modem_serial, phone):
                response = f"Звоним {contacts_db.find_by_name_or_alias(name)[0][1]}."
                say(response)
            else:
                response = "Не удалось инициировать звонок."
                say(response)
        elif use_mock:
            display_name = contacts_db.find_by_name_or_alias(name)
            response = f"Демо: звоним {display_name[0][1] if display_name else name}."
            say(response)
        else:
            response = f"Звоним {name}: {phone}. Модем не подключён."
            say(response)
        return response

    if matched.action == "call_number":
        number = matched.slot_value
        if not number:
            response = "Назовите номер."
            say(response)
            return response
        if modem_serial:
            from src.modem import call as modem_call
            if modem_call.dial(modem_serial, number):
                response = "Набираю номер."
                say(response)
            else:
                response = "Не удалось набрать номер."
                say(response)
        elif use_mock:
            response = f"Демо: набираю номер {number}."
            say(response)
        else:
            response = f"Модем не подключён. Номер: {number}."
            say(response)
        return response

    if matched.action == "hangup":
        if modem_serial:
            from src.modem import call as modem_call
            modem_call.hangup(modem_serial)
        response = "Звонок завершён."
        say(response)
        return response

    if matched.action == "answer":
        if modem_serial:
            from src.modem import call as modem_call
            modem_call.answer(modem_serial)
        response = "Принимаю звонок."
        say(response)
        return response

    if matched.action == "read_sms":
        if modem_serial:
            from src.modem import sms as modem_sms
            messages = modem_sms.list_sms(modem_serial)
            if not messages:
                response = "Нет сообщений."
            else:
                parts = [f"От {m.sender}: {m.text[:80]}" for m in messages[:5]]
                response = " ".join(parts)
            say(response)
        elif use_mock:
            response = "Демо: нет новых сообщений."
            say(response)
        else:
            response = "Модем не подключён."
            say(response)
        return response

    if matched.action == "list_contacts":
        contacts = contacts_db.list_all_contacts()
        if not contacts:
            response = "Контакты пусты."
        else:
            names = [c[1] for c in contacts[:15]]
            response = "Контакты: " + ", ".join(names)
        say(response)
        return response

    if matched.action == "what_time":
        from datetime import datetime
        now = datetime.now()
        response = f"Сейчас {now.hour} часов {now.minute} минут."
        say(response)
        return response

    if matched.action == "help":
        response = (
            "Можно сказать: позвони контакту, набери номер, список контактов, "
            "прочитай смс, который час, положи трубку, ответь на звонок."
        )
        say(response)
        return response

    if matched.action == "signal":
        if modem_serial:
            from src.modem import at_commands as at
            rssi, _ = at.get_signal_quality(modem_serial)
            if rssi is not None:
                if rssi == 99:
                    response = "Уровень сигнала неизвестен."
                else:
                    response = f"Уровень сигнала: {rssi} из 31."
            else:
                response = "Не удалось получить уровень сигнала."
            say(response)
        elif use_mock:
            response = "Демо: уровень сигнала 15 из 31."
            say(response)
        else:
            response = "Модем не подключён."
            say(response)
        return response

    return response
