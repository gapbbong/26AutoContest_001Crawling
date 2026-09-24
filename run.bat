@echo off
cd /d "%~dp0"
chcp 65001 > nul
cls
echo Starting Exam Generator...
python main.py
if errorlevel 1 pause
