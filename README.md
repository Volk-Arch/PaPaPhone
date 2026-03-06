# PaPaPhone

Голосовой телефон на Orange Pi Zero 2W + SIM7600G-H 4G HAT (Waveshare). Управление голосом: звонки по контактам, набор номера, SMS, контакты, время, уровень сигнала.

## Технологии

- **Python 3** — основное приложение
- **Vosk** — офлайн распознавание речи
- **SQLite** — хранение контактов (имя, номер, алиасы для голоса)
- **pyttsx3 + eSpeak** — офлайн озвучка ответов
- **pyserial** — работа с модулем SIM7600 по AT-командам
- **Словарь команд** — YAML (`data/commands.yaml`)

## Требования

- Orange Pi Zero 2W (или ПК для разработки)
- SIM7600G-H 4G HAT, подключённый по UART/USB
- Микрофон (USB или совместимый с ALSA)
- Динамик/наушники для TTS

### Системные пакеты (Debian/Orange Pi)

```bash
sudo apt install espeak ffmpeg libportaudio2 portaudio19-dev
```

## Установка

```bash
cd PaPaPhone
python -m venv .venv
.venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Модель Vosk

Скачайте малую модель для русского или английского и распакуйте в папку `models/`:

- Русская: [vosk-model-small-ru-0.22](https://alphacephei.com/vosk/models)
- Английская: [vosk-model-small-en-us-0.15](https://alphacephei.com/vosk/models)

Имя папки должно совпадать с конфигом (по умолчанию `vosk-model-small-ru-0.22`). Можно задать через переменную окружения:

```bash
export PAPAPHONE_VOSK_MODEL=vosk-model-small-en-us-0.15
```

## Конфигурация

В [src/config.py](src/config.py) или через переменные окружения:

- `PAPAPHONE_MODEM_PORT` — порт модуля (на Orange Pi: `/dev/ttyUSB0` или `/dev/ttyS1`, смотреть `dmesg | grep tty`)
- `PAPAPHONE_VOSK_MODEL` — имя папки модели в `models/`
- `PAPAPHONE_WAKE_PHRASES` — команды-активаторы через запятую (по умолчанию `телефон,папафон`)
- `PAPAPHONE_AUDIO_INPUT_DEVICE` / `PAPAPHONE_AUDIO_OUTPUT_DEVICE` — индекс устройства ALSA при необходимости

## Запуск

Из корня проекта:

```bash
python -m src.main
```

Опции:

- `--no-modem` — не подключаться к модему (удобно для локального теста: контакты, время, помощь, плюс в консоль выводится «Распознано: …»)
- `--no-asr` — не загружать Vosk (если нет микрофона)
- `--listen-timeout 12` — таймаут ожидания фразы в секундах
- `--test-asr` — только проверка Vosk: без модема и TTS, распознанный текст выводится в консоль (для отладки распознавания)
- `--test-asr-say` — вместе с `--test-asr`: после каждой фразы озвучивать ответ («Вы сказали: …» или «Не расслышала»), чтобы проверить и TTS
- `--demo` — **демо-режим**: без модема, с имитацией звонков/SMS/сигнала; полный цикл (Vosk → команды → TTS) для проверки на ПК
- `--no-wake` — не требовать команду «телефон» перед основными командами (всегда сразу слушать команды)

По умолчанию приложение ждёт **команду-активатор** («телефон» или «папафон»), затем говорит «Слушаю» и принимает основную команду (позвони, контакты, который час и т.д.). С флагом `--no-wake` можно сразу говорить команды без активатора.

После старта приложение говорит «Готов к командам» (или «Демо-режим. Готов к командам» при `--demo`) и ждёт голосовые команды. Скажите, например: «Позвони Ивану», «Список контактов», «Который час», «Помощь».

### Если TTS не озвучивает

- **Windows**: нужны голоса SAPI (обычно уже есть). Если пишет про драйвер — установите [eSpeak для Windows](https://github.com/rhasspy/espeak-ng/releases) и перезапустите.
- **Linux**: установите `espeak`: `sudo apt install espeak ffmpeg`.
- При ошибке инициализации движка фразы выводятся в консоль с префиксом `[TTS]` — так можно проверить логику без звука.

## Добавление контактов

База SQLite в `data/papaphone.db`. Контакты можно добавлять программно:

```python
from src.contacts import db
db.init_db()
db.add_contact("Иван Петров", "+79001234567", aliases=["Иван", "Ваня"])
```

Или через свой скрипт/админку, используя `contacts.db`: `add_contact`, `find_by_name_or_alias`, `list_all_contacts`.

## Структура проекта

```
PaPaPhone/
├── src/
│   ├── main.py           # Точка входа
│   ├── config.py         # Конфигурация
│   ├── voice/            # Vosk (asr) + pyttsx3 (tts)
│   ├── modem/            # SIM7600: serial_io, at_commands, call, sms
│   ├── contacts/        # SQLite контакты
│   └── commands/        # Словарь команд (YAML) и исполнитель
├── data/
│   ├── commands.yaml    # Фразы и действия
│   └── papaphone.db     # База контактов (создаётся при первом запуске)
├── models/              # Сюда положить модель Vosk (в .gitignore)
├── requirements.txt
└── README.md
```

## Лицензия

Проект в репозитории — по вашему выбору. Vosk, pyttsx3, eSpeak и др. — по их лицензиям.
