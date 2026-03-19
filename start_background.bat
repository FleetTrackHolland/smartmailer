@echo off
REM SmartMailer Ultimate — Gorunmez Arka Plan Servisi
REM Chrome kapatilsa bile calisir, pencere gostermez
cd /d "%~dp0"
start /b pythonw main.py --dashboard --port 5000
echo SmartMailer arka planda baslatildi!
echo Task Manager'dan "pythonw.exe" ile durdurabilirsiniz.
timeout /t 3 /nobreak >nul
