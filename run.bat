@echo off
chcp 65001 >nul
title 凝华 · Rubedo

echo ========================================
echo   凝华 · Rubedo v0.2.0
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] 检查依赖...
python -c "import nicegui, apscheduler, sqlalchemy, pywebview" 2>nul
if %errorlevel% neq 0 (
    echo [!] 缺少依赖，正在安装...
    pip install nicegui apscheduler sqlalchemy pywebview
)
echo.

echo [2/2] 启动凝华...
python app.py

pause
