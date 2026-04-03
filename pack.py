#!/usr/bin/env python3
"""
pack.py — подготовить бандл для переноса на устройство.

Работает на Windows, Linux, macOS.
Скачивает модели (если нет), собирает код + модели + pip-пакеты в архив.

Использование:
  python pack.py
Результат:
  papaphone-bundle.tar.gz — один файл, содержит всё.
"""
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from urllib.request import urlretrieve

PROJECT_ROOT = Path(__file__).resolve().parent
MODELS_DIR = PROJECT_ROOT / "models"
BUNDLE_DIR = Path(os.environ.get("TEMP", "/tmp")) / "papaphone-bundle"
ARCHIVE = PROJECT_ROOT / "papaphone-bundle.tar.gz"

# Модели для скачивания
VOSK_MODEL = os.environ.get("PAPAPHONE_VOSK_MODEL", "vosk-model-small-ru-0.22")
VOSK_URL = f"https://alphacephei.com/vosk/models/{VOSK_MODEL}.zip"
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/ruslan/medium"
NAVEC_URL = "https://storage.yandexcloud.net/natasha-navec/packs/navec_hudlit_v1_12B_500K_300d_100q.tar"

GREEN = "\033[92m"
YELLOW = "\033[93m"
NC = "\033[0m"


def info(msg):
    print(f"{GREEN}[INFO]{NC} {msg}")


def warn(msg):
    print(f"{YELLOW}[WARN]{NC} {msg}")


def download(url, dest):
    """Скачать файл с прогрессом."""
    if dest.exists():
        info(f"Уже есть: {dest.name}")
        return True
    info(f"Скачиваю: {dest.name}...")
    try:
        urlretrieve(url, str(dest))
        size_mb = dest.stat().st_size / 1e6
        info(f"Скачано: {dest.name} ({size_mb:.0f} MB)")
        return True
    except Exception as e:
        warn(f"Не удалось скачать {dest.name}: {e}")
        return False


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Модели ──
    info("=== Модели ===")

    # Vosk
    vosk_dir = MODELS_DIR / VOSK_MODEL
    vosk_zip = MODELS_DIR / f"{VOSK_MODEL}.zip"
    if vosk_dir.exists():
        info(f"Vosk: {VOSK_MODEL} (уже есть)")
    elif vosk_zip.exists():
        info(f"Распаковываю {vosk_zip.name}...")
        shutil.unpack_archive(str(vosk_zip), str(MODELS_DIR))
    else:
        if download(VOSK_URL, vosk_zip):
            info(f"Распаковываю {vosk_zip.name}...")
            shutil.unpack_archive(str(vosk_zip), str(MODELS_DIR))
        else:
            warn(f"Скачайте вручную: {VOSK_URL}")
            warn(f"Положите zip в {MODELS_DIR}/")

    # Piper
    piper_onnx = MODELS_DIR / "ru_RU-ruslan-medium.onnx"
    piper_json = MODELS_DIR / "ru_RU-ruslan-medium.onnx.json"
    download(f"{PIPER_BASE}/ru_RU-ruslan-medium.onnx", piper_onnx)
    download(f"{PIPER_BASE}/ru_RU-ruslan-medium.onnx.json", piper_json)

    # Navec
    navec_tar = MODELS_DIR / "navec_hudlit_v1_12B_500K_300d_100q.tar"
    download(NAVEC_URL, navec_tar)

    # ── 2. Pip-пакеты ──
    info("=== Pip-пакеты ===")
    pip_dir = BUNDLE_DIR / "pip-packages"
    pip_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "download",
             "-r", str(PROJECT_ROOT / "requirements.txt"),
             "-d", str(pip_dir), "--quiet"],
            check=False, capture_output=True,
        )
        pkg_count = len(list(pip_dir.glob("*")))
        info(f"Скачано {pkg_count} пакетов")
    except Exception as e:
        warn(f"pip download: {e}")

    # ── 3. Собираем бандл ──
    info("=== Сборка бандла ===")
    project_dest = BUNDLE_DIR / "PaPaPhone"
    if project_dest.exists():
        shutil.rmtree(project_dest)

    # Копируем проект
    ignore = shutil.ignore_patterns(
        ".venv", "__pycache__", "*.pyc", ".git", "papaphone.db",
        "papaphone-bundle.tar.gz", ".env",
    )
    shutil.copytree(str(PROJECT_ROOT), str(project_dest), ignore=ignore)

    # install.sh
    install_script = BUNDLE_DIR / "install.sh"
    install_script.write_text(INSTALL_SH, encoding="utf-8")

    # ── 4. Архив ──
    info("Создаю архив...")
    with tarfile.open(str(ARCHIVE), "w:gz") as tar:
        tar.add(str(BUNDLE_DIR), arcname="papaphone-bundle")

    shutil.rmtree(BUNDLE_DIR)
    size_mb = ARCHIVE.stat().st_size / 1e6

    print()
    print(f"{GREEN}{'=' * 50}{NC}")
    print(f"{GREEN}  Бандл готов: {ARCHIVE.name} ({size_mb:.0f} MB){NC}")
    print(f"{GREEN}{'=' * 50}{NC}")
    print()
    print("Перенос на устройство:")
    print(f"  scp {ARCHIVE.name} user@device:~/")
    print()
    print("На устройстве:")
    print("  tar xzf papaphone-bundle.tar.gz")
    print("  cd papaphone-bundle")
    print("  bash install.sh")


INSTALL_SH = r"""#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }

INSTALL_DIR="${1:-$HOME/PaPaPhone}"
info "Установка PaPaPhone в $INSTALL_DIR..."

sudo apt-get update -q 2>/dev/null || true
sudo apt-get install -y python3 python3-pip python3-venv portaudio19-dev libasound2-dev 2>/dev/null || warn "Некоторые пакеты не установились"
groups "$USER" | grep -q dialout || sudo usermod -aG dialout "$USER"

if [ -d "$INSTALL_DIR" ]; then
    info "Обновляю существующую установку..."
    rsync -a --exclude='data/papaphone.db' --exclude='data/.env' "$SCRIPT_DIR/PaPaPhone/" "$INSTALL_DIR/"
else
    cp -r "$SCRIPT_DIR/PaPaPhone" "$INSTALL_DIR"
fi

VENV="$INSTALL_DIR/.venv"
python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip -q

if [ -d "$SCRIPT_DIR/pip-packages" ] && [ "$(ls -A $SCRIPT_DIR/pip-packages 2>/dev/null)" ]; then
    info "Устанавливаю пакеты из бандла..."
    pip install --no-index --find-links="$SCRIPT_DIR/pip-packages" -r "$INSTALL_DIR/requirements.txt" -q 2>/dev/null || \
    pip install -r "$INSTALL_DIR/requirements.txt" -q
else
    pip install -r "$INSTALL_DIR/requirements.txt" -q
fi

if [ ! -f "$INSTALL_DIR/data/.env" ]; then
    cp "$INSTALL_DIR/data/.env.example" "$INSTALL_DIR/data/.env"
    info "Создан data/.env"
fi

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
echo "Настройка:  nano $INSTALL_DIR/data/.env"
echo "Запуск:     sudo systemctl start papaphone"
echo "Логи:       journalctl -u papaphone -f"
"""


if __name__ == "__main__":
    main()
