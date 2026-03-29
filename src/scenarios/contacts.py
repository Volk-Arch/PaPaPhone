# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Сценарии управления контактами.

AddContactScenario  — добавить контакт голосом (пошаговый ввод номера)
FindContactScenario — найти контакт и предложить позвонить
DeleteContactScenario — удалить контакт (секретное меню)
"""
import re
import sys

from src.contacts import db as contacts_db
from src.scenarios.base import (
    BaseScenario,
    ScenarioContext,
    CONFIRM_TIMEOUT,
    is_cancel,
    CancelledError,
)

# Слова-команды при вводе номера
_REDO_WORDS = ("неправильно", "заново", "ошибка", "не то", "нет", "сброс", "назад")
_DONE_WORDS = ("готово", "всё", "все", "конец", "дальше", "достаточно")

# Максимум цифр (рос. номер: +7 + 10 = 11, или 8 + 10 = 11)
_MAX_DIGITS = 11

# Русские числительные → строка цифр (включая составные)
_COMPOUND_NUMBERS = {
    "двадцать": "2", "тридцать": "3", "сорок": "4", "пятьдесят": "5",
    "шестьдесят": "6", "семьдесят": "7", "восемьдесят": "8", "девяносто": "9",
    "сто": "1",  # "сто" в контексте номера = "100" но мы берём цифры
}

_WORD_TO_DIGIT = {
    "ноль": "0", "нуль": "0", "нулевой": "0",
    "один": "1", "одна": "1", "раз": "1", "первый": "1", "первая": "1",
    "два": "2", "две": "2", "второй": "2", "вторая": "2",
    "три": "3", "третий": "3", "третья": "3",
    "четыре": "4", "четвёрка": "4",
    "пять": "5", "пятёрка": "5",
    "шесть": "6", "шестёрка": "6",
    "семь": "7", "семёрка": "7",
    "восемь": "8", "восьмёрка": "8",
    "девять": "9", "девятка": "9",
    "десять": "10",
    "одиннадцать": "11", "двенадцать": "12", "тринадцать": "13",
    "четырнадцать": "14", "пятнадцать": "15", "шестнадцать": "16",
    "семнадцать": "17", "восемнадцать": "18", "девятнадцать": "19",
    "двадцать": "20", "тридцать": "30", "сорок": "40",
    "пятьдесят": "50", "шестьдесят": "60", "семьдесят": "70",
    "восемьдесят": "80", "девяносто": "90", "сто": "100",
    "плюс": "+",
}


def _extract_digits(text: str) -> str:
    """Извлечь ВСЕ цифры из произнесённого текста.

    Поддерживает:
    - Числительные: "восемь" → "8", "десять" → "10"
    - Несколько слов: "восемь девять ноль" → "890"
    - Цифры: "89001234567" → "89001234567"
    - Составные: "двадцать три" → "23" (десятки + единицы)
    - Плюс: "плюс" → "+"

    Возвращает строку цифр (может быть пустой).
    """
    t = text.lower().strip()
    words = t.split()
    result = []

    # Сначала ищем числительные пословно (целые слова, не подстроки!)
    i = 0
    while i < len(words):
        w = words[i]

        # Плюс
        if w == "плюс" or w == "+":
            result.append("+")
            i += 1
            continue

        # Проверяем числительное (длинные первыми для приоритета)
        matched = False
        for word, digits in sorted(_WORD_TO_DIGIT.items(), key=lambda x: len(x[0]), reverse=True):
            if w == word:
                # Составное: "двадцать" + "три" → "2" + "3" (а не "20" + "3")
                val = int(digits) if digits.isdigit() else 0
                if val >= 20 and val % 10 == 0 and val < 100:
                    # Десятки — проверяем есть ли единицы следом
                    tens_digit = str(val // 10)
                    if i + 1 < len(words):
                        next_w = words[i + 1]
                        for nw, nd in _WORD_TO_DIGIT.items():
                            if next_w == nw and nd.isdigit() and 1 <= int(nd) <= 9:
                                result.append(tens_digit + nd)
                                i += 2
                                matched = True
                                break
                    if not matched:
                        result.append(digits)
                        i += 1
                        matched = True
                else:
                    result.append(digits)
                    i += 1
                    matched = True
                break

        if matched:
            continue

        # Ищем цифры внутри слова
        d = re.findall(r"\d+", w)
        if d:
            result.extend(d)

        i += 1

    return "".join(result)


class AddContactScenario(BaseScenario):
    """Добавить контакт: имя голосом, номер — по цифрам или группами."""

    def run(self, ctx: ScenarioContext) -> None:
        # Шаг 1: имя
        ctx.tts.say("Назовите имя контакта.")
        name_raw = self._listen(ctx, ctx.listen_timeout)
        if not name_raw or not name_raw.strip():
            ctx.tts.say("Имя не распознано. Отменено.")
            return
        name = name_raw.strip()

        # Проверка дубликата
        existing = contacts_db.find_by_name_or_alias(name)
        if existing:
            ctx.tts.say(f"Контакт {existing[0][1]} уже есть в книге.")
            return

        # Шаг 2: номер
        ctx.tts.say(
            f"Имя: {name}. Диктуйте номер — можно по одной цифре или группами. "
            "Скажите «неправильно» чтобы стереть последнюю. "
            "Скажите «готово» когда закончите. Для отмены скажите «стоп»."
        )

        digits: list[str] = []
        while True:
            how_many = len(digits)
            ctx.tts.say(f"Введено {how_many}. Следующая.", block=True)
            text = self._listen(ctx, ctx.listen_timeout)

            if not text or not text.strip():
                ctx.tts.say("Не расслышала. Повторите.")
                continue

            t = text.lower().strip()
            print(f"[DIGITS] Распознано: «{t}», набрано: {how_many}", file=sys.stderr)

            # Проверка на «готово»
            if any(w in t for w in _DONE_WORDS):
                if len(digits) < 7:
                    ctx.tts.say(
                        f"Введено {len(digits)} цифр. Нужно минимум 7. Продолжайте."
                    )
                    continue
                break

            # Проверка на «неправильно» / «назад»
            if any(w in t for w in _REDO_WORDS):
                if digits:
                    removed = digits.pop()
                    current = " ".join(digits) if digits else "пусто"
                    ctx.tts.say(f"Убрала {removed}. Набрано: {current}.")
                else:
                    ctx.tts.say("Номер пуст.")
                continue

            # Извлекаем цифры (одну или несколько)
            extracted = _extract_digits(t)
            if not extracted or extracted == "+":
                ctx.tts.say("Не поняла. Скажите цифру, например «восемь» или «пять».")
                continue

            # Добавляем посимвольно
            for ch in extracted:
                if ch == "+" or ch.isdigit():
                    digits.append(ch)

            ctx.tts.say(f"{'  '.join(extracted)}.", block=True)

            # Проговорить накопленное каждые 4 цифры
            if len(digits) >= 4 and len(digits) % 4 == 0:
                ctx.tts.say(f"Набрано: {' '.join(digits)}.")

            # Автостоп на 11 цифрах
            if len(digits) >= _MAX_DIGITS:
                ctx.tts.say(f"Набрано {len(digits)} цифр — номер полный.")
                break

        number = "".join(digits)
        spoken = " ".join(digits)

        # Шаг 3: подтверждение
        if not self._confirm(
            ctx,
            f"Добавить контакт {name}, номер {spoken}. Да или нет?",
        ):
            return

        # Шаг 4: алиас (необязательно)
        ctx.tts.say(
            f"Как ещё называть {name}? Например сын или мама. "
            "Скажите «нет» чтобы пропустить."
        )
        alias_raw = self._listen(ctx, ctx.listen_timeout)
        aliases = []
        if alias_raw and alias_raw.strip():
            a = alias_raw.lower().strip()
            if a not in ("нет", "не надо", "пропустить", "нету"):
                # Проверка: не занято ли прозвище другим контактом
                conflict = contacts_db.find_by_name_or_alias(a)
                if conflict:
                    ctx.tts.say(
                        f"Прозвище {a} уже используется для {conflict[0][1]}. Пропускаю."
                    )
                else:
                    aliases.append(a)
                    ctx.tts.say(f"Прозвище: {a}.")

        contacts_db.add_contact(name, number, aliases=aliases if aliases else None)
        ctx.tts.say(f"Контакт {name} добавлен.")


class AliasContactScenario(BaseScenario):
    """Добавить прозвище к существующему контакту."""

    def __init__(self, contact_name: str) -> None:
        self._name = contact_name

    def run(self, ctx: ScenarioContext) -> None:
        results = contacts_db.find_by_name_or_alias(self._name)
        if not results:
            ctx.tts.say(f"Контакт {self._name} не найден.")
            return

        _id, display, phone = results[0]

        ctx.tts.say(f"Контакт {display}. Скажите прозвище.")
        alias_raw = self._listen(ctx, ctx.listen_timeout)
        if not alias_raw or not alias_raw.strip():
            ctx.tts.say("Не расслышала. Отменено.")
            return

        alias = alias_raw.lower().strip()

        # Проверка: не занято ли другим контактом
        conflict = contacts_db.find_by_name_or_alias(alias)
        if conflict and conflict[0][0] != _id:
            ctx.tts.say(
                f"Прозвище {alias} уже используется для {conflict[0][1]}."
            )
            return

        if self._confirm(ctx, f"Добавить прозвище {alias} для {display}? Да или нет."):
            import json
            conn = contacts_db._get_connection()
            try:
                row = conn.execute(
                    "SELECT aliases FROM contacts WHERE id = ?", (_id,)
                ).fetchone()
                current = json.loads(row["aliases"] or "[]") if row else []
                if alias in current:
                    ctx.tts.say(f"{display} уже откликается на {alias}.")
                else:
                    current.append(alias)
                    contacts_db.update_contact(_id, aliases=current)
                    ctx.tts.say(f"Прозвище {alias} добавлено для {display}.")
            finally:
                conn.close()


_FIND_CALL_WORDS = ("позвони", "позвонить", "звонок", "да")
_FIND_ALIAS_WORDS = ("прозвище",)
_FIND_RENAME_WORDS = ("переименуй", "переименовать", "имя")


class FindContactScenario(BaseScenario):
    """Найти контакт → позвонить, прозвище или переименовать."""

    def __init__(self, contact_name: str) -> None:
        self._name = contact_name

    def run(self, ctx: ScenarioContext) -> None:
        results = contacts_db.find_by_name_or_alias(self._name)

        if not results:
            ctx.tts.say(f"Контакт {self._name} не найден.")
            return

        _id, display, phone = results[0]

        ctx.tts.say(
            f"Контакт {display}. "
            "Позвонить, прозвище, или переименовать?"
        )
        answer = self._listen(ctx, CONFIRM_TIMEOUT)
        if not answer or not answer.strip():
            ctx.tts.say("Не расслышала.")
            return

        a = answer.lower().strip()

        if any(w in a for w in _FIND_CALL_WORDS):
            from src.scenarios.call import CallContactScenario
            CallContactScenario(display).run(ctx)
            return

        if any(w in a for w in _FIND_ALIAS_WORDS):
            AliasContactScenario(display).run(ctx)
            return

        if any(w in a for w in _FIND_RENAME_WORDS):
            ctx.tts.say(f"Как назвать {display}? Скажите новое имя.")
            new_name = self._listen(ctx, ctx.listen_timeout)
            if not new_name or not new_name.strip():
                ctx.tts.say("Не расслышала. Отменено.")
                return
            new_name = new_name.strip()
            # Проверка дубликата
            conflict = contacts_db.find_by_name_or_alias(new_name)
            if conflict and conflict[0][0] != _id:
                ctx.tts.say(f"Имя {new_name} уже занято контактом {conflict[0][1]}.")
                return
            if self._confirm(ctx, f"Переименовать {display} в {new_name}? Да или нет."):
                contacts_db.update_contact(_id, name=new_name)
                ctx.tts.say(f"Контакт переименован в {new_name}.")
            return

        ctx.tts.say("Не поняла.")


_DELETE_WORDS = ("удали", "удалить", "убери", "убрать")
_EMERGENCY_ADD_WORDS = ("экстренный", "экстренным", "важный", "важным", "добавь")
_EMERGENCY_DEL_WORDS = ("убрать из экстренных", "убрать из важных", "не экстренный")
_EXIT_WORDS = ("выход", "выйти", "назад", "всё")


class SecretMenuScenario(BaseScenario):
    """Секретное меню: найти контакт -> удалить или сделать экстренным.

    Вход по фразе "секретное меню".
    Цикл: назови имя -> нашли -> удалить / сделать экстренным / выход.
    """

    def run(self, ctx: ScenarioContext) -> None:
        ctx.tts.say(
            "Секретное меню. Назовите имя контакта. "
            "Скажите «выход» чтобы выйти."
        )

        while True:
            answer = self._listen(ctx, ctx.listen_timeout)
            if not answer or not answer.strip():
                ctx.tts.say("Не расслышала. Назовите имя или скажите выход.")
                continue

            a = answer.lower().strip()

            if any(w in a for w in _EXIT_WORDS):
                ctx.tts.say("Выход из секретного меню.")
                return

            results = contacts_db.find_by_name_or_alias(a)
            if not results:
                ctx.tts.say(f"Контакт {a} не найден. Попробуйте другое имя.")
                continue

            _id, display, phone = results[0]

            # Читаем is_emergency из БД
            all_emergency = contacts_db.get_emergency_contacts()
            is_emergency = any(eid == _id for eid, _, _ in all_emergency)
            status = " Экстренный." if is_emergency else ""

            ctx.tts.say(
                f"Контакт {display}.{status} "
                "Скажите «удалить», «экстренный», или «убрать из экстренных»."
            )
            action = self._listen(ctx, CONFIRM_TIMEOUT)
            if not action or not action.strip():
                ctx.tts.say("Не расслышала. Назовите другой контакт или выход.")
                continue

            act = action.lower().strip()

            if any(w in act for w in _DELETE_WORDS):
                if self._confirm(ctx, f"Удалить {display}? Да или нет."):
                    contacts_db.delete_contact(_id)
                    ctx.tts.say(f"Контакт {display} удалён.")
                ctx.tts.say("Назовите следующий контакт или выход.")
                continue

            # "убрать из экстренных" проверяем РАНЬШЕ чем "экстренный"
            if any(w in act for w in _EMERGENCY_DEL_WORDS):
                if is_emergency:
                    contacts_db.set_emergency(_id, False)
                    ctx.tts.say(f"{display} убран из экстренных.")
                else:
                    ctx.tts.say(f"{display} не в экстренных.")
                ctx.tts.say("Назовите следующий контакт или выход.")
                continue

            if any(w in act for w in _EMERGENCY_ADD_WORDS):
                if is_emergency:
                    ctx.tts.say(f"{display} уже экстренный.")
                else:
                    contacts_db.set_emergency(_id, True)
                    ctx.tts.say(f"{display} добавлен в экстренные.")
                ctx.tts.say("Назовите следующий контакт или выход.")
                continue

            ctx.tts.say("Не поняла. Назовите другой контакт или выход.")
