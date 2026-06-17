@echo off
REM One-command backend launcher (cmd.exe / PowerShell). Uses the project's
REM venv Python directly so you don't have to activate the venv first.
REM Forwards extra args to main.py (e.g. run.bat --port 9000).

setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py %*
    exit /b %ERRORLEVEL%
)

echo error: no virtualenv found. Run setup first:
echo   python -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -e .
exit /b 1
