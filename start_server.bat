@echo off
title SmartMailer Ultimate — Background Server
echo ============================================
echo   SmartMailer Ultimate — Arka Plan Servisi
echo ============================================
echo.
echo Chrome kapatilsa bile calisir!
echo Durdurmak icin: Ctrl+C veya Task Manager
echo ============================================
echo.

cd /d "%~dp0"

:start
echo [%date% %time%] Server baslatiliyor...
python main.py --dashboard --port 5000
echo.
echo [%date% %time%] Server durdu! 10sn sonra yeniden baslatiliyor...
timeout /t 10 /nobreak >nul
goto start
