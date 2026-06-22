@echo off
REM Time Tracker 启动脚本 v0.1
REM 双击运行，无需命令行知识

cd /d "%~dp0"
python time_tracker.py
if errorlevel 1 (
    echo.
    echo [错误] 无法启动时间记录工具。
    echo 请确保已安装 Python，或在命令行运行：python time_tracker.py
    pause
)
