@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === Выгрузка в GitHub: Nero-AI- ===
echo.

REM Проверка Git
git --version >nul 2>&1
if errorlevel 1 (
    echo ОШИБКА: Git не найден! Установите Git: https://git-scm.com/download/win
    pause
    exit /b 1
)

REM Инициализация (если ещё нет .git)
if not exist ".git" (
    echo Инициализация Git...
    git init
)

REM Имя и email для Git (обязательно для коммита!)
REM Замените на свои данные или введите вручную перед push
git config user.email "Nikolaygiit@users.noreply.github.com" 2>nul
git config user.name "Nikolaygiit" 2>nul

REM Исправление remote origin (удаляем старый, добавляем правильный)
git remote remove origin 2>nul
git remote add origin https://github.com/Nikolaygiit/Nero-AI-.git

REM Добавление файлов
echo Добавление файлов...
git add .

REM Коммит (без коммита ветка main не создаётся!)
echo Создание коммита...
git commit -m "Initial commit: Telegram bot with Gemini AI"
if errorlevel 1 (
    echo Коммит уже существует или нет изменений.
)

REM Ветка main
git branch -M main

REM Push
echo Выгрузка на GitHub...
git push -u origin main

if errorlevel 1 (
    echo.
    echo Если push не прошёл, возможно нужна авторизация.
    echo 1. GitHub может запросить логин/пароль - используйте Personal Access Token вместо пароля
    echo 2. Или настройте SSH: https://docs.github.com/en/authentication
    echo.
) else (
    echo.
    echo Готово! Репозиторий: https://github.com/Nikolaygiit/Nero-AI-
)

pause
