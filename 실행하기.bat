@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo [Error] Python was not found on PATH. Please install Python 3.10+ and try again.
    pause
    exit /b 1
)
start "" pythonw "%~dp0main.py"
exit
