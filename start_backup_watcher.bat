@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === Наблюдатель резервного копирования ===
echo Каждые 5 изменений → копия в папку "Проект 3 (Git Копия)"
echo.

REM Проверка watchdog
python -c "import watchdog" 2>nul
if errorlevel 1 (
    echo Установка watchdog...
    pip install watchdog
)

echo Запуск наблюдателя... Нажмите Ctrl+C для остановки.
echo.
python backup_watcher.py

pause
