@echo off
REM Telegram AC Bot Auto-Startup Script
REM This will start your bot automatically when Windows starts

REM Set paths
set PYTHON_PATH=C:\Python312\python.exe
set SCRIPT_DIR=C:\Users\user\Documents\Workplace Interview\PayPal\kaggle
set BOT_SCRIPT=%SCRIPT_DIR%\telegrram.py

REM Create logs directory
if not exist "C:\temp" mkdir "C:\temp"

REM Change to script directory
cd /d "%SCRIPT_DIR%"

REM Start logging
echo ============================================ >> "C:\temp\telegram_bot_startup.log"
echo %date% %time% - Bot startup script started >> "C:\temp\telegram_bot_startup.log"
echo ============================================ >> "C:\temp\telegram_bot_startup.log"

:start_bot
echo %date% %time% - Starting Telegram AC Bot... >> "C:\temp\telegram_bot_startup.log"
echo Starting Telegram AC Bot...

REM Start the bot and redirect output to log file
"%PYTHON_PATH%" "%BOT_SCRIPT%" >> "C:\temp\telegram_bot.log" 2>&1

REM If we get here, the bot stopped/crashed
echo %date% %time% - Bot stopped. Restarting in 10 seconds... >> "C:\temp\telegram_bot_startup.log"
echo Bot stopped. Restarting in 10 seconds...

REM Wait 10 seconds before restarting
timeout /t 10 /nobreak >nul

REM Restart the bot
goto start_bot