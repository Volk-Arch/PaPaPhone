# PaPaPhone

Голосовой телефон на Orange Pi + SIM7600 4G HAT. Управление только голосом — для людей, которым сложно пользоваться смартфоном.

## Возможности

- 📞 Звонки по имени из книги контактов или по номеру
- 📲 Ответ и сброс входящих звонков голосом
- 💬 Чтение SMS по одному с паузами
- 👤 Добавление контактов голосом
- 🕐 Время, уровень сигнала, список контактов
- 🔔 Автообнаружение входящих звонков (AT+CLCC)

Все действия детерминированы: каждый сценарий — чёткий диалог с подтверждением. Молчание или непонимание → отмена (безопасный дефолт).

## Технологии

| Компонент | Технология |
|---|---|
| Распознавание речи | [Vosk](https://alphacephei.com/vosk/) (офлайн) |
| Синтез речи | [Piper TTS](https://github.com/rhasspy/piper) (офлайн, нейросеть) |
| Модем | SIM7600 по AT-командам (pyserial) |
| Контакты | SQLite |
| Команды | YAML-словарь + fuzzy match |

## Оборудование

- Orange Pi Zero 2W (или любой Linux ARM/x86)
- SIM7600G-H 4G HAT, подключённый по UART/USB
- USB-микрофон (или совместимый с ALSA)
- Динамик (USB-аудио или 3.5 мм)

## Установка

```bash
bash deploy.sh
```

Скрипт сам установит системные пакеты, создаст venv, скачает модели Vosk и Piper, создаст systemd-сервис.

### Ручная установка

```bash
# Системные зависимости
sudo apt install python3 python3-venv portaudio19-dev

# Виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Модель Vosk (русская, ~50 МБ)
mkdir -p models
wget https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip
unzip vosk-model-small-ru-0.22.zip -d models/

# Модель Piper (русская, ~60 МБ)
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/ruslan/medium
wget -P models/ $BASE/ru_RU-ruslan-medium.onnx
wget -P models/ $BASE/ru_RU-ruslan-medium.onnx.json
```

## Запуск

```bash
# Обычный запуск
python -m src.main

# Без wake-фразы (сразу слушает команды)
python -m src.main --no-wake

# Демо-режим — без модема и TTS, вывод в консоль (тест на ПК)
python -m src.main --demo

# Без модема (только контакты, время, помощь — TTS работает)
python -m src.main --no-modem
```

### Управление сервисом (после deploy.sh)

```bash
sudo systemctl start papaphone
sudo systemctl stop papaphone
journalctl -u papaphone -f   # логи в реальном времени
```

## Голосовые команды

После wake-фразы **«телефон»** скажите:

| Команда | Что происходит |
|---|---|
| «позвони маме» | Ищет контакт → подтверждение → звонит |
| «набери 9 1 6 1 2 3 4 5 6 7» | Подтверждение → набирает номер |
| «положи трубку» | Завершает звонок |
| «ответь» | Отвечает на входящий |
| «прочитай смс» | Читает сообщения по одному |
| «добавь контакт» | 3 шага: имя → номер → подтверждение |
| «список контактов» | Называет все имена |
| «который час» | Говорит время |
| «уровень сигнала» | Говорит качество сети |
| «помощь» | Перечисляет команды |

**Входящий звонок**: система сама обнаруживает через AT+CLCC каждые 3 секунды, объявляет кто звонит, спрашивает «Ответить?». При молчании — сброс.

## Конфигурация

Через переменные окружения (или `src/config.py`):

| Переменная | По умолчанию | Описание |
|---|---|---|
| `PAPAPHONE_MODEM_PORT` | `/dev/ttyUSB0` | Порт SIM7600 |
| `PAPAPHONE_VOSK_MODEL` | `vosk-model-small-ru-0.22` | Папка модели Vosk в `models/` |
| `PAPAPHONE_PIPER_MODEL` | `models/ru_RU-ruslan-medium.onnx` | Путь к модели Piper |
| `PAPAPHONE_PIPER_SAMPLE_RATE` | `22050` | Частота дискретизации Piper |
| `PAPAPHONE_AUDIO_INPUT_DEVICE` | (системный) | Индекс ALSA-устройства записи |
| `PAPAPHONE_AUDIO_OUTPUT_DEVICE` | (системный) | Индекс ALSA-устройства воспроизведения |
| `PAPAPHONE_WAKE_PHRASES` | `телефон,папафон` | Wake-фразы через запятую |

Доступные ALSA-устройства: `aplay -l` (воспроизведение), `arecord -l` (запись).

## Структура проекта

```
PaPaPhone/
├── src/
│   ├── main.py              # Точка входа, главный цикл
│   ├── config.py            # Конфигурация через env
│   ├── voice/
│   │   ├── asr.py           # Vosk: распознавание речи
│   │   └── tts.py           # Piper: синтез речи
│   ├── modem/
│   │   ├── serial_io.py     # UART / AT-команды
│   │   ├── at_commands.py   # Инициализация, сигнал
│   │   ├── call.py          # Звонки, определитель номера
│   │   └── sms.py           # Чтение SMS
│   ├── contacts/
│   │   ├── db.py            # SQLite CRUD + поиск по имени/номеру
│   │   └── schema.sql
│   ├── commands/
│   │   ├── dictionary.py    # Загрузка YAML-словаря
│   │   └── executor.py      # match_command() → MatchedCommand
│   └── scenarios/
│       ├── base.py          # ScenarioContext, BaseScenario, _confirm()
│       ├── call.py          # Звонки + ожидание конца разговора
│       ├── info.py          # Время, помощь, контакты, сигнал
│       ├── sms.py           # Чтение SMS по одному
│       ├── contacts.py      # Добавление контакта голосом
│       └── __init__.py      # get_scenario(text) — роутер
├── data/
│   ├── commands.yaml        # Фразы и действия
│   └── papaphone.db         # База контактов (создаётся автоматически)
├── models/                  # Модели Vosk и Piper (.gitignore)
├── requirements.txt
├── deploy.sh                # Установка на Orange Pi
└── README.md
```

## Автор

**Igor Kriusov** — [kriusovia@gmail.com](mailto:kriusovia@gmail.com)
GitHub: [https://github.com/Volk-Arch/PaPaPhone](https://github.com/Volk-Arch/PaPaPhone)

## Лицензия

Код проекта: **[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)** — бесплатно для личного и некоммерческого использования.

Зависимости: Vosk (Apache 2.0), Piper TTS (MIT), остальные — см. их репозитории.
