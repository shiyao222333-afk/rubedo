@echo off
chcp 65001 >nul
title 凝华 · Rubedo

echo ========================================
echo   凝华 · Rubedo v0.2.0 平台基建
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 检查 NiceGUI
python -c "import nicegui" >nul 2>&1
if %errorlevel% neq 0 (
    echo [安装] 正在安装 NiceGUI...
    pip install nicegui
    if %errorlevel% neq 0 (
        echo [错误] NiceGUI 安装失败
        pause
        exit /b 1
    )
)

:: 启动应用
echo [启动] 正在启动凝华...
echo.
python app.py
set EXIT_CODE=%errorlevel%

if %EXIT_CODE% NEQ 0 (
    echo.
    echo ===================================================
    echo   应用异常退出（退出码 %EXIT_CODE%）
    echo   请查看上方错误信息
    echo ===================================================
    pause
    cmd /k
)

echo.
echo [停止] 应用已停止。
pause
