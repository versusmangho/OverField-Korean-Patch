@echo off
cd /d "%~dp0"
python translator_gui.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Execution failed.
    pause
)
