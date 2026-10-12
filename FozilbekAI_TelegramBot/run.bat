@echo off
chcp 65001 >nul
title FOZILBEK AI TELEGRAM BOT

echo ======================================
echo       FOZILBEK AI TELEGRAM BOT
echo ======================================
echo.

REM ==================================================
REM BOT PAPKASIGA O'TISH
REM ==================================================

cd /d "%~dp0"

echo [OK] Bot papkasi:
echo %CD%
echo.

REM ==================================================
REM PYTHON 3.11 TEKSHIRISH
REM ==================================================

py -3.11 --version >nul 2>&1

if errorlevel 1 (
    echo.
    echo [X] Python 3.11 topilmadi!
    echo.
    echo O'rnatilgan Pythonlarni tekshirish:
    echo py -0p
    echo.
    pause
    exit /b 1
)

echo [OK] Python:
py -3.11 --version
echo.

REM ==================================================
REM PIP
REM ==================================================

echo [1/2] Kerakli kutubxonalar tekshirilmoqda...
echo.

py -3.11 -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [X] Kutubxonalarni o'rnatishda xatolik!
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Kutubxonalar tayyor.
echo.

REM ==================================================
REM BOT
REM ==================================================

echo [2/2] Telegram bot ishga tushmoqda...
echo.

echo ======================================
echo       BOT ISHLAYAPTI
echo       Python 3.11
echo       To'xtatish: Ctrl+C
echo ======================================
echo.

py -3.11 -u bot.py

echo.
echo ======================================
echo       BOT TO'XTADI
echo ======================================
echo.

pause