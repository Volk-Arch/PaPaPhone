#!/usr/bin/env bash
# deploy.sh — установка PaPaPhone на Orange Pi (Armbian/Ubuntu ARM)
# Запуск: bash deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
MODELS_DIR="$SCRIPT_DIR/models"

# ── Цвета для вывода ────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Системные зависимости ───────────────────────────────────────────────────
info "Обновление пакетов и установка системных зависимостей..."
sudo apt-get update -q
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    portaudio19-dev \
    libgomp1 \
    libasound2-dev \
    curl wget \
    2>/dev/null || warn "Некоторые пакеты не установились — продолжаем"

# ── Добавить пользователя в группу dialout (доступ к /dev/ttyUSB*) ──────────
if ! groups "$USER" | grep -q dialout; then
    info "Добавление $USER в группу dialout (для доступа к модему)..."
    sudo usermod -aG dialout "$USER"
    warn "Перезайдите в систему чтобы изменения вступили в силу, затем запустите deploy.sh снова."
fi

# ── Python venv ─────────────────────────────────────────────────────────────
info "Создание виртуального окружения Python..."
python3 -m venv "$VENV"
source "$VENV/bin/activate"

info "Установка Python-зависимостей..."
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt"

# ── Vosk модель ─────────────────────────────────────────────────────────────
# Модель Vosk: лёгкая по умолчанию (45 MB)
# Для точности: export PAPAPHONE_VOSK_MODEL=vosk-model-ru-0.42 (1.8 GB)
VOSK_MODEL_NAME="${PAPAPHONE_VOSK_MODEL:-vosk-model-small-ru-0.22}"
VOSK_MODEL_PATH="$MODELS_DIR/$VOSK_MODEL_NAME"

if [ -d "$VOSK_MODEL_PATH" ]; then
    info "Модель Vosk уже есть: $VOSK_MODEL_PATH"
else
    mkdir -p "$MODELS_DIR"
    VOSK_URL="https://alphacephei.com/vosk/models/${VOSK_MODEL_NAME}.zip"
    VOSK_ZIP="/tmp/vosk_model.zip"

    # Проверяем: может zip уже залит вручную в models/
    if [ -f "$MODELS_DIR/${VOSK_MODEL_NAME}.zip" ]; then
        info "Найден zip в models/, распаковываю..."
        VOSK_ZIP="$MODELS_DIR/${VOSK_MODEL_NAME}.zip"
    else
        info "Скачивание модели Vosk ($VOSK_MODEL_NAME)..."
        wget --timeout=30 -q --show-progress -O "$VOSK_ZIP" "$VOSK_URL" 2>/dev/null
        if [ $? -ne 0 ] || [ ! -f "$VOSK_ZIP" ]; then
            warn "Не удалось скачать модель Vosk автоматически."
            echo ""
            echo "Скачайте вручную и положите в models/:"
            echo "  1. Скачайте: $VOSK_URL"
            echo "  2. Скопируйте zip на устройство: scp ${VOSK_MODEL_NAME}.zip user@device:$(pwd)/models/"
            echo "  3. Запустите deploy.sh ещё раз — он распакует автоматически."
            echo ""
            # Не прерываем — остальное можно поставить
            VOSK_ZIP=""
        fi
    fi

    if [ -n "$VOSK_ZIP" ] && [ -f "$VOSK_ZIP" ]; then
        unzip -q "$VOSK_ZIP" -d "$MODELS_DIR"
        # Удаляем zip только если он был во /tmp
        [ "$VOSK_ZIP" = "/tmp/vosk_model.zip" ] && rm -f "$VOSK_ZIP"
        info "Модель Vosk установлена: $VOSK_MODEL_PATH"
    fi
fi

# ── Piper TTS и модель ───────────────────────────────────────────────────────
PIPER_MODEL_ONNX="$MODELS_DIR/ru_RU-ruslan-medium.onnx"
PIPER_MODEL_JSON="$MODELS_DIR/ru_RU-ruslan-medium.onnx.json"

# Проверить что piper доступен после pip install
if ! command -v piper &>/dev/null; then
    warn "Команда 'piper' не найдена в PATH. Проверьте: $VENV/bin/piper"
fi

if [ -f "$PIPER_MODEL_ONNX" ] && [ -f "$PIPER_MODEL_JSON" ]; then
    info "Модель Piper уже есть: $PIPER_MODEL_ONNX"
else
    info "Скачивание модели Piper (ru_RU-ruslan-medium)..."
    mkdir -p "$MODELS_DIR"
    BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/ruslan/medium"
    wget -q --show-progress -O "$PIPER_MODEL_ONNX"      "${BASE_URL}/ru_RU-ruslan-medium.onnx"      || warn "Не удалось скачать .onnx — скачайте вручную"
    wget -q --show-progress -O "$PIPER_MODEL_JSON"      "${BASE_URL}/ru_RU-ruslan-medium.onnx.json"  || warn "Не удалось скачать .onnx.json — скачайте вручную"
    info "Модель Piper установлена."
fi

# ── Navec модель (эмбеддинги для нечёткого поиска) ───────────────────────────
NAVEC_MODEL="$MODELS_DIR/navec_hudlit_v1_12B_500K_300d_100q.tar"
if [ -f "$NAVEC_MODEL" ]; then
    info "Модель Navec уже есть."
else
    info "Скачивание модели Navec (50 MB)..."
    mkdir -p "$MODELS_DIR"
    wget -q --show-progress -O "$NAVEC_MODEL" \
        "https://storage.yandexcloud.net/natasha-navec/packs/navec_hudlit_v1_12B_500K_300d_100q.tar" \
        || warn "Не удалось скачать Navec — нечёткий поиск будет только по Левенштейну"
fi

# ── Конфигурация (.env) ──────────────────────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/data/.env"
ENV_EXAMPLE="$SCRIPT_DIR/data/.env.example"

if [ -f "$ENV_FILE" ]; then
    info "Конфигурация уже есть: $ENV_FILE"
else
    info "Первый запуск — настройка конфигурации."
    cp "$ENV_EXAMPLE" "$ENV_FILE"

    # Адрес
    echo ""
    read -rp "Домашний адрес (для экстренных служб): " _addr
    if [ -n "$_addr" ]; then
        sed -i "s|^PAPAPHONE_HOME_ADDRESS=.*|PAPAPHONE_HOME_ADDRESS=$_addr|" "$ENV_FILE"
    fi

    # Порт модема
    DETECTED_PORT=$(ls /dev/ttyUSB* 2>/dev/null | head -1)
    if [ -n "$DETECTED_PORT" ]; then
        info "Обнаружен модем: $DETECTED_PORT"
        sed -i "s|^PAPAPHONE_MODEM_PORT=.*|PAPAPHONE_MODEM_PORT=$DETECTED_PORT|" "$ENV_FILE"
    fi

    info "Конфигурация сохранена: $ENV_FILE"
    info "Отредактировать позже: nano $ENV_FILE"
fi

# ── Проверка звука ───────────────────────────────────────────────────────────
info "Доступные аудиоустройства ALSA:"
aplay -l 2>/dev/null | grep "^card" || warn "aplay не нашёл устройств. Проверьте USB-аудио."

# ── Systemd сервис ───────────────────────────────────────────────────────────
SERVICE_FILE="/etc/systemd/system/papaphone.service"
CURRENT_USER="$USER"

info "Создание systemd-сервиса..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=PaPaPhone — голосовой телефон
After=network.target sound.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${VENV}/bin/python -m src.main
Restart=always
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=10
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable papaphone.service
info "Сервис papaphone.service создан и включён."

# ── Финал ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  Установка завершена!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "Команды управления:"
echo "  sudo systemctl start papaphone    — запустить"
echo "  sudo systemctl stop papaphone     — остановить"
echo "  sudo systemctl status papaphone   — статус"
echo "  journalctl -u papaphone -f        — логи в реальном времени"
echo ""
echo "Ручной запуск для теста:"
echo "  source $VENV/bin/activate"
echo "  python -m src.main --demo         # без модема"
echo "  python -m src.main --demo --no-wake"
echo ""
echo "Конфигурация:  nano $SCRIPT_DIR/data/.env"
echo ""
