@echo off
cd /d "%~dp0"

py -3.11 -u bot.py >> bot_log.txt 2>&1