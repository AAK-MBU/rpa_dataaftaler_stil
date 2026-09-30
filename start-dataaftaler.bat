@echo off
REM Double-click launcher for the Dataaftaler - STIL desktop app.
REM First run installs uv (if missing) and the dependencies; later runs are fast.
REM The file is UTF-8 with CRLF line endings; chcp 65001 makes the console print æøå.
chcp 65001 >nul
cd /d "%~dp0"

REM Relaunch in its own classic console window (conhost), so Windows Terminal
REM cannot open the launcher as a tab in an already open terminal window.
if /i not "%~1"=="--own-window" if exist "%SystemRoot%\System32\conhost.exe" (
    start "" "%SystemRoot%\System32\conhost.exe" cmd.exe /c ""%~f0" --own-window"
    exit /b
)

REM The setup wizard opens when .env has no RUN_MODE yet (see gui/app.py).
set "FIRST_SETUP=1"
if exist ".env" findstr /b /i /c:"RUN_MODE=" ".env" >nul 2>nul && set "FIRST_SETUP="

REM --- Step 1: find or install uv (one-time) ---
echo Step 1/3 - Finder uv (Python-værktøjet)...
where uv >nul 2>nul && goto :have_uv
echo Installerer uv (engangsopsætning)...
powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
REM uv installs to %USERPROFILE%\.local\bin by default; add it for this session.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

:have_uv
REM --- Step 2: install/update dependencies ---
echo Step 2/3 - Klargører programmet (kan tage lidt tid første gang)...
uv sync || (echo. & echo Fejl under installation. Kontakt support. & pause & exit /b 1)

REM --- Step 3: launch windowless via the synced venv, then close this console ---
echo Step 3/3 - Starter programmet...
start "" ".venv\Scripts\pythonw.exe" -m gui.app

if defined FIRST_SETUP (
    echo.
    echo Gør klar til opsætning, vent på pop up vindue når dette vindue lukkes
    REM Keep the message readable for a moment before the console closes.
    timeout /t 5 /nobreak >nul
)
exit
