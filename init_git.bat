@echo off
chcp 65001 >nul
cd /d "%~dp0"
git init
echo.
echo Git инициализирован в папке проекта.
echo Для первого коммита выполните:
echo   git add .
echo   git commit -m "Initial commit"
pause
