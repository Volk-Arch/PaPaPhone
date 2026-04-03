@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   PaPaPhone: сборка бандла для устройства
echo ============================================
echo.

set "PROJECT_DIR=%~dp0"
set "MODELS_DIR=%PROJECT_DIR%models"
set "BUNDLE_DIR=%TEMP%\papaphone-bundle"
set "ARCHIVE=%PROJECT_DIR%papaphone-bundle.tar.gz"

:: Проверяем tar (есть в Windows 10+)
where tar >nul 2>&1 || (
    echo ОШИБКА: tar не найден. Нужен Windows 10 1803+
    pause
    exit /b 1
)

:: Очистка
if exist "%BUNDLE_DIR%" rmdir /s /q "%BUNDLE_DIR%"
mkdir "%BUNDLE_DIR%\PaPaPhone"

:: ── 1. Копируем проект ──
echo [INFO] Копирую проект...
robocopy "%PROJECT_DIR%" "%BUNDLE_DIR%\PaPaPhone" /e /xd .venv __pycache__ .git /xf *.pyc papaphone.db papaphone-bundle.tar.gz .env >nul

:: ── 2. Модели ──
echo [INFO] Проверяю модели...

set "VOSK_MODEL=vosk-model-small-ru-0.22"
if defined PAPAPHONE_VOSK_MODEL set "VOSK_MODEL=%PAPAPHONE_VOSK_MODEL%"

if exist "%MODELS_DIR%\%VOSK_MODEL%" (
    echo [INFO] Vosk: %VOSK_MODEL% OK
) else (
    echo [WARN] Vosk модель не найдена: %MODELS_DIR%\%VOSK_MODEL%
    echo        Скачайте: https://alphacephei.com/vosk/models/%VOSK_MODEL%.zip
    echo        Распакуйте в models\
)

if exist "%MODELS_DIR%\ru_RU-ruslan-medium.onnx" (
    echo [INFO] Piper: OK
) else (
    echo [WARN] Piper модель не найдена.
)

if exist "%MODELS_DIR%\navec_hudlit_v1_12B_500K_300d_100q.tar" (
    echo [INFO] Navec: OK
) else (
    echo [WARN] Navec модель не найдена. Нечёткий поиск только по Левенштейну.
)

:: ── 3. Pip-пакеты (если есть Python) ──
where python >nul 2>&1 && (
    echo [INFO] Скачиваю pip-пакеты...
    mkdir "%BUNDLE_DIR%\pip-packages" 2>nul
    python -m pip download -r "%PROJECT_DIR%requirements.txt" -d "%BUNDLE_DIR%\pip-packages" --quiet 2>nul
    echo [INFO] Pip-пакеты готовы.
) || (
    echo [WARN] Python не найден, pip-пакеты не скачаны. Устройству нужен интернет.
)

:: ── 4. install.sh уже в проекте (скопирован robocopy) ──

:: ── 5. Архив ──
echo [INFO] Создаю архив...
pushd "%TEMP%"
tar -czf "%ARCHIVE%" papaphone-bundle
popd

rmdir /s /q "%BUNDLE_DIR%"

for %%A in ("%ARCHIVE%") do set "SIZE=%%~zA"
set /a SIZE_MB=%SIZE% / 1048576

echo.
echo ============================================
echo   Бандл готов: papaphone-bundle.tar.gz (%SIZE_MB% MB)
echo ============================================
echo.
echo Перенос на устройство:
echo   scp papaphone-bundle.tar.gz user@device:~/
echo.
echo На устройстве:
echo   tar xzf papaphone-bundle.tar.gz
echo   cd papaphone-bundle
echo   bash install.sh
echo.
pause
