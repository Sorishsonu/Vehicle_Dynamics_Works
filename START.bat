@echo off
cd /d "%~dp0"
python -m pip install openpyxl pillow
if errorlevel 1 (pause & exit /b 1)
python app.py
pause
