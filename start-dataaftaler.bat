@echo off
REM Double-click launcher for the Dataaftaler - STIL desktop app.
REM First run installs uv (if missing) and the dependencies; later runs are fast.
REM The file is UTF-8 with CRLF line endings; chcp 65001 makes the console print æøå.
chcp 65001 >nul
cd /d "%~dp0"

REM Fast path: when the setup is done and the dependencies match the current
REM uv.lock/pyproject.toml, start the app straight away without the setup console.
set "SYNC_MARK=.venv\.synced"
if not exist ".venv\Scripts\pythonw.exe" goto :full_start
if not exist ".env" goto :full_start
findstr /b /i /c:"RUN_MODE=" ".env" >nul 2>nul || goto :full_start
fc /b "uv.lock" "%SYNC_MARK%-uv.lock" >nul 2>nul || goto :full_start
fc /b "pyproject.toml" "%SYNC_MARK%-pyproject.toml" >nul 2>nul || goto :full_start
start "" ".venv\Scripts\pythonw.exe" -m gui.app
exit

:full_start

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
REM Remember what was synced so the next start can take the fast path.
copy /y "uv.lock" "%SYNC_MARK%-uv.lock" >nul
copy /y "pyproject.toml" "%SYNC_MARK%-pyproject.toml" >nul

REM --- Step 3: launch windowless via the synced venv ---
REM The app creates READY_FILE once its first window is shown (see
REM gui/app.py); this console waits for it so the user is not left without
REM feedback while Python starts.
set "READY_FILE=%TEMP%\dataaftaler_ready_%RANDOM%%RANDOM%.flag"
del "%READY_FILE%" >nul 2>nul
set "DATAAFTALER_READY_FILE=%READY_FILE%"

echo Step 3/3 - Starter programmet...
start "" ".venv\Scripts\pythonw.exe" -m gui.app

echo.
if defined FIRST_SETUP (
    echo Gør klar til opsætning. Vent på opsætningsvinduet – dette vindue lukker, når det er åbent.
) else (
    echo Venter på programvinduet – dette vindue lukker, når det er åbent.
)

set /a WAITED=0
set /a MAX_WAIT=180

:wait_loop
if exist "%READY_FILE%" goto :ready
if %WAITED% geq %MAX_WAIT% goto :not_ready
timeout /t 1 /nobreak >nul
set /a WAITED+=1
set /a TICK=WAITED %% 5
if %TICK%==0 call :waiting_message
goto :wait_loop

:waiting_message
set /a MSG=(WAITED / 5) %% 3
if %MSG%==1 echo Vent stadig, den er på vej... (%WAITED% sek.)
if %MSG%==2 echo Programmet indlæses stadig... (%WAITED% sek.)
if %MSG%==0 echo Næsten klar, bliv ved med at vente... (%WAITED% sek.)
exit /b

:ready
del "%READY_FILE%" >nul 2>nul
exit

:not_ready
echo.
echo Programvinduet er ikke dukket op efter %MAX_WAIT% sekunder.
echo Hvis det ikke åbner, så luk dette vindue og prøv igen, eller kontakt support.
pause
exit
