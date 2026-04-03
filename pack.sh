#!/usr/bin/env bash
# pack.sh — подготовить всё для переноса на устройство без интернета.
# Запуск на компьютере: bash pack.sh
# Результат: papaphone-bundle.tar.gz — один файл, содержит всё.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="/tmp/papaphone-bundle"
MODELS_DIR="$SCRIPT_DIR/models"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"

# ── 1. Код проекта ──────────────────────────────────────────────────────────
info "Копирую код проекта..."
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.git' --exclude='data/papaphone.db' --exclude='data/.env' \
    "$SCRIPT_DIR/" "$BUNDLE_DIR/PaPaPhone/"

# ── 2. Модели ───────────────────────────────────────────────────────────────
VOSK_MODEL="${PAPAPHONE_VOSK_MODEL:-vosk-model-small-ru-0.22}"
VOSK_PATH="$MODELS_DIR/$VOSK_MODEL"
PIPER_ONNX="$MODELS_DIR/ru_RU-ruslan-medium.onnx"
NAVEC_MODEL="$MODELS_DIR/navec_hudlit_v1_12B_500K_300d_100q.tar"

mkdir -p "$BUNDLE_DIR/PaPaPhone/models"

if [ -d "$VOSK_PATH" ]; then
    info "Vosk модель: $VOSK_MODEL"
    cp -r "$VOSK_PATH" "$BUNDLE_DIR/PaPaPhone/models/"
else
    warn "Vosk модель не найдена: $VOSK_PATH"
    warn "Скачайте: https://alphacephei.com/vosk/models/${VOSK_MODEL}.zip"
fi

if [ -f "$PIPER_ONNX" ]; then
    info "Piper модель: OK"
    cp "$PIPER_ONNX" "$BUNDLE_DIR/PaPaPhone/models/"
    cp "${PIPER_ONNX}.json" "$BUNDLE_DIR/PaPaPhone/models/" 2>/dev/null || true
else
    warn "Piper модель не найдена. Скачайте с huggingface."
fi

if [ -f "$NAVEC_MODEL" ]; then
    info "Navec модель: OK"
    cp "$NAVEC_MODEL" "$BUNDLE_DIR/PaPaPhone/models/"
else
    warn "Navec модель не найдена. Нечёткий поиск будет только по Левенштейну."
fi

# ── 3. Python пакеты (pip download) ────────────────────────────────────────
info "Скачиваю pip-пакеты для офлайн установки..."
mkdir -p "$BUNDLE_DIR/pip-packages"
pip download -r "$SCRIPT_DIR/requirements.txt" \
    -d "$BUNDLE_DIR/pip-packages" \
    --quiet 2>/dev/null || warn "Некоторые пакеты не скачались (ARM пакеты скачаются на устройстве)"

# ── 4. Скрипт установки на устройстве ──────────────────────────────────────
cat > "$BUNDLE_DIR/install.sh" << 'INSTALL_EOF'
#!/usr/bin/env bash
# install.sh — установка из бандла на устройстве (без интернета).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }

INSTALL_DIR="${1:-$HOME/PaPaPhone}"

info "Установка PaPaPhone в $INSTALL_DIR..."

# Системные пакеты
sudo apt-get update -q 2>/dev/null || true
sudo apt-get install -y python3 python3-pip python3-venv portaudio19-dev libasound2-dev 2>/dev/null || warn "Некоторые пакеты не установились"

# Группа dialout
groups "$USER" | grep -q dialout || sudo usermod -aG dialout "$USER"

# Копируем проект
if [ -d "$INSTALL_DIR" ]; then
    info "Обновляю существующую установку..."
    rsync -a --exclude='data/papaphone.db' --exclude='data/.env' \
        "$SCRIPT_DIR/PaPaPhone/" "$INSTALL_DIR/"
else
    cp -r "$SCRIPT_DIR/PaPaPhone" "$INSTALL_DIR"
fi

# Venv + пакеты
VENV="$INSTALL_DIR/.venv"
python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip -q

# Сначала офлайн пакеты, потом онлайн (если нужны ARM-специфичные)
if [ -d "$SCRIPT_DIR/pip-packages" ] && [ "$(ls -A $SCRIPT_DIR/pip-packages)" ]; then
    info "Устанавливаю пакеты из бандла..."
    pip install --no-index --find-links="$SCRIPT_DIR/pip-packages" \
        -r "$INSTALL_DIR/requirements.txt" -q 2>/dev/null || \
    pip install -r "$INSTALL_DIR/requirements.txt" -q
else
    info "Устанавливаю пакеты из интернета..."
    pip install -r "$INSTALL_DIR/requirements.txt" -q
fi

# Конфигурация
if [ ! -f "$INSTALL_DIR/data/.env" ]; then
    cp "$INSTALL_DIR/data/.env.example" "$INSTALL_DIR/data/.env"
    info "Создан data/.env — отредактируйте: nano $INSTALL_DIR/data/.env"
fi

# Systemd
SERVICE_FILE="/etc/systemd/system/papaphone.service"
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=PaPaPhone
After=network.target sound.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV/bin/python -m src.main
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

echo ""
echo -e "${GREEN}Установка завершена!${NC}"
echo ""
echo "Настройка:  nano $INSTALL_DIR/data/.env"
echo "Запуск:     sudo systemctl start papaphone"
echo "Логи:       journalctl -u papaphone -f"
INSTALL_EOF
chmod +x "$BUNDLE_DIR/install.sh"

# ── 5. Архив ────────────────────────────────────────────────────────────────
ARCHIVE="$SCRIPT_DIR/papaphone-bundle.tar.gz"
info "Создаю архив..."
tar -czf "$ARCHIVE" -C /tmp papaphone-bundle
rm -rf "$BUNDLE_DIR"

SIZE=$(du -h "$ARCHIVE" | cut -f1)
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  Бандл готов: $ARCHIVE ($SIZE)${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "Перенос на устройство:"
echo "  scp $ARCHIVE user@device:~/"
echo ""
echo "На устройстве:"
echo "  tar xzf papaphone-bundle.tar.gz"
echo "  cd papaphone-bundle"
echo "  bash install.sh"
