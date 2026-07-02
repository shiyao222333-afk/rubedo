@echo off
chcp 437 >nul
title Rubedo v0.3.0

echo ================================
echo   Rubedo v0.3.0 - SOP Platform
echo ================================
echo.

:: Kill old process on port 8081 (fix "only one usage of socket" error)
powershell -Command "Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1
powershell -Command "Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*rubedo*' -or $_.MainWindowTitle -like '*rubedo*' } | Stop-Process -Force -ErrorAction SilentlyContinue" >nul 2>&1
timeout /t 2 >nul

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 goto no_python

:: Check dependencies
python -c "import nicegui, apscheduler, starlette" >nul 2>&1
if %errorlevel% equ 0 goto deps_ok

echo [INSTALL] Installing dependencies...
pip install nicegui APScheduler
if %errorlevel% neq 0 goto install_fail

:deps_ok

:: Start app
echo [START] Starting Rubedo...
echo.
python app.py
set EXIT_CODE=%errorlevel%
if %EXIT_CODE% NEQ 0 goto error_exit
goto normal_exit

:no_python
echo [ERROR] Python not found. Please install Python 3.10+
pause
exit /b 1

:install_fail
echo [ERROR] Dependency installation failed
pause
exit /b 1

:error_exit
echo.
echo ===================================================
echo   App exited abnormally (exit code %EXIT_CODE%)
echo   Check error messages above
echo ===================================================
pause
cmd /k

:normal_exit
echo.
echo [STOP] App stopped.
pause
