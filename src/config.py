"""
Конфигурация PaPaPhone.
Пути и параметры задаются здесь или через переменные окружения.
"""
import os
from pathlib import Path

# Корень проекта (каталог с README.md)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Модель Vosk: имя папки в models/ (скачать с https://alphacephei.com/vosk/models)
# Примеры: vosk-model-small-ru-0.22, vosk-model-small-en-us-0.15
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

# Аудио: устройство записи/воспроизведения (None = по умолчанию в системе)
# На Orange Pi задать индекс ALSA при необходимости, например 1 для USB-микрофона
AUDIO_INPUT_DEVICE = os.environ.get("PAPAPHONE_AUDIO_INPUT_DEVICE")
AUDIO_OUTPUT_DEVICE = os.environ.get("PAPAPHONE_AUDIO_OUTPUT_DEVICE")

# Параметры записи для Vosk: 16 kHz моно, как рекомендует Vosk
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE_MS = 4000  # размер блока в мс для AcceptWaveform

# Язык по умолчанию (для подсказок и словаря команд)
LANG = os.environ.get("PAPAPHONE_LANG", "ru")

# Команда-активатор: после неё принимаются основные команды (позвони, контакты и т.д.)
_wa = os.environ.get("PAPAPHONE_WAKE_PHRASES", "телефон,папафон")
WAKE_PHRASES = [p.strip().lower() for p in _wa.split(",") if p.strip()]
