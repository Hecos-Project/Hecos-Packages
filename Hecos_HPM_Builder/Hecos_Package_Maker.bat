@echo off
title Hecos Package Manager (HPM) Builder
color 0B

:: Force UTF-8 in the Windows console
chcp 65001 >nul

:: Ensure we are in the directory of the batch file
cd /d "%~dp0"

echo Avvio di HPM Builder Toolkit in corso...

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Python non e' installato o non si trova nelle variabili d'ambiente PATH.
    echo Assicurati di installare Python e selezionare "Add Python to PATH".
    pause
    exit /b
)

:: Run the CLI
python main.py

:: Prevent closing if the script crashes
echo.
pause
