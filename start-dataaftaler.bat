@echo off
REM Double-click launcher for the Dataaftaler - STIL desktop app.
REM First run installs uv (if missing) and the dependencies; later runs are fast.
cd /d "%~dp0"

REM --- Find or install uv (one-time) ---
where uv >nul 2>nul && goto :have_uv
echo Installerer uv (engangsopsaetning)...
powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
REM uv installs to %USERPROFILE%\.local\bin by default; add it for this session.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

:have_uv
echo Klargør programmet (kan tage lidt tid første gang)...
uv sync || (echo. & echo Fejl under installation. Kontakt support. & pause & exit /b 1)

REM Launch windowless via the synced venv, then close this console.
start "" ".venv\Scripts\pythonw.exe" -m gui.app
exit
