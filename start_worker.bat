@echo off
chcp 65001 >nul
echo Запуск воркера очередей (Taskiq + Redis)...
echo Обрабатываются задачи: генерация изображений и т.д.
echo.
python -m tasks.worker
if errorlevel 1 (
    echo.
    echo Ошибка: убедитесь, что Redis запущен (redis-server) и установлены зависимости.
    pause
)
