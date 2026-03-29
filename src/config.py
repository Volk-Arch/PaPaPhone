# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# https://polyformproject.org/licenses/noncommercial/1.0.0/
"""
Конфигурация PaPaPhone.
Параметры загружаются из data/.env (если есть), потом из переменных окружения.
"""
import os
from pathlib import Path

# Корень проекта (каталог с README.md)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Загрузить .env файл если есть (без внешних зависимостей)
_ENV_FILE = PROJECT_ROOT / "data" / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#"):
                continue
            if "=" in _line:
                _key, _, _val = _line.partition("=")
                _key = _key.strip()
                _val = _val.strip().strip('"').strip("'")
                # Не перезаписываем уже заданные env (приоритет у shell)
                if _key not in os.environ:
                    os.environ[_key] = _val

# Модель Vosk: имя папки в models/ (скачать с https://alphacephei.com/vosk/models)
#   vosk-model-small-ru-0.22  — 45 MB, ~300 MB RAM (быстрая, лёгкая)
#   vosk-model-ru-0.42        — 1.8 GB, ~3-4 GB RAM (точнее, но тяжёлая)
VOSK_MODEL_NAME = os.environ.get("PAPAPHONE_VOSK_MODEL", "vosk-model-small-ru-0.22")
VOSK_MODEL_PATH = PROJECT_ROOT / "models" / VOSK_MODEL_NAME

# Последовательный порт модуля SIM7600 (на Orange Pi: /dev/ttyUSB0 или /dev/ttyS1)
MODEM_PORT = os.environ.get("PAPAPHONE_MODEM_PORT", "/dev/ttyUSB0")
MODEM_BAUDRATE = 115200
MODEM_TIMEOUT_READ_S = 2.0
MODEM_TIMEOUT_WRITE_S = 1.0

# База контактов и словарь команд
DATA_DIR = PROJECT_ROOT / "data"
CONTACTS_DB_PATH = DATA_DIR / "papaphone.db"
COMMANDS_YAML_PATH = DATA_DIR / "commands.yaml"

# Экстренный вызов: номер по умолчанию 112 (единая служба спасения РФ)
EMERGENCY_NUMBER = os.environ.get("PAPAPHONE_EMERGENCY_NUMBER", "112")

# Адрес проживания — озвучивается по команде «адрес» (для экстренных служб)
HOME_ADDRESS = os.environ.get(
    "PAPAPHONE_HOME_ADDRESS",
    "Адрес не задан. Установите переменную PAPAPHONE_HOME_ADDRESS.",
)

# Аудио: устройство записи/воспроизведения (None = по умолчанию в системе)
# На Orange Pi задать индекс ALSA при необходимости, например 1 для USB-микрофона
AUDIO_INPUT_DEVICE = os.environ.get("PAPAPHONE_AUDIO_INPUT_DEVICE")
AUDIO_OUTPUT_DEVICE = os.environ.get("PAPAPHONE_AUDIO_OUTPUT_DEVICE")

# Piper TTS: путь к .onnx модели и частота дискретизации
# Скачать модель: https://huggingface.co/rhasspy/piper-voices/
# Пример модели: ru_RU-ruslan-medium.onnx (+ .onnx.json рядом)
PIPER_MODEL_PATH = Path(
    os.environ.get(
        "PAPAPHONE_PIPER_MODEL",
        str(PROJECT_ROOT / "models" / "ru_RU-ruslan-medium.onnx"),
    )
)
PIPER_SAMPLE_RATE = int(os.environ.get("PAPAPHONE_PIPER_SAMPLE_RATE", "22050"))

# Параметры записи для Vosk: 16 kHz моно, как рекомендует Vosk
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE_MS = 4000  # размер блока в мс для AcceptWaveform

# Язык по умолчанию (для подсказок и словаря команд)
LANG = os.environ.get("PAPAPHONE_LANG", "ru")

# Команда-активатор: после неё принимаются основные команды (позвони, контакты и т.д.)
_wa = os.environ.get("PAPAPHONE_WAKE_PHRASES", "телефон,папафон")
WAKE_PHRASES = [p.strip().lower() for p in _wa.split(",") if p.strip()]
