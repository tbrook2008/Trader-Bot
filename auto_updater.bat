@echo off
echo Starting Topstep Bot Auto-Updater...

:loop
REM Fetch latest from remote
git fetch origin main >nul 2>&1

REM Check if there are updates
FOR /F "tokens=*" %%a IN ('git rev-parse HEAD') DO SET LOCAL=%%a
FOR /F "tokens=*" %%a IN ('git rev-parse origin/main') DO SET REMOTE=%%a

if NOT "%LOCAL%"=="%REMOTE%" (
    echo Updates found! Pulling latest code...
    git pull origin main
    
    REM Kill the bot if it is running
    taskkill /F /IM python.exe /T >nul 2>&1
)

REM Check if python is running
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="1" (
    echo Starting bot...
    start /B python -m bot.ivan_trader
)

REM Wait 60 seconds
timeout /t 60 /nobreak >nul
goto loop
