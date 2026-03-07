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
VOSK_MODEL_NAME="vosk-model-small-ru-0.22"
VOSK_MODEL_PATH="$MODELS_DIR/$VOSK_MODEL_NAME"

if [ -d "$VOSK_MODEL_PATH" ]; then
    info "Модель Vosk уже есть: $VOSK_MODEL_PATH"
else
    info "Скачивание модели Vosk ($VOSK_MODEL_NAME)..."
    mkdir -p "$MODELS_DIR"
    VOSK_URL="https://alphacephei.com/vosk/models/${VOSK_MODEL_NAME}.zip"
    wget -q --show-progress -O /tmp/vosk_model.zip "$VOSK_URL" || \
        error "Не удалось скачать модель Vosk. Скачайте вручную: $VOSK_URL"
    unzip -q /tmp/vosk_model.zip -d "$MODELS_DIR"
    rm /tmp/vosk_model.zip
    info "Модель Vosk установлена: $VOSK_MODEL_PATH"
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
Restart=on-failure
RestartSec=5
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
echo "  python -m src.main --demo         # без модема и TTS"
echo "  python -m src.main --no-wake      # без wake-фразы"
echo ""
echo "Если нужен другой аудиовыход, задайте:"
echo "  export PAPAPHONE_AUDIO_OUTPUT_DEVICE=<индекс ALSA>"
echo "  export PAPAPHONE_AUDIO_INPUT_DEVICE=<индекс ALSA>"
echo ""
