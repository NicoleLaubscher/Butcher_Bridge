@echo off
setlocal
cd /d "%~dp0"
title ButcherBridge

rem --- find Python ---
set PY=
where py >nul 2>nul && set PY=py
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
  echo Python was not found. Install it from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

rem --- create venv + install packages on first run ---
if not exist "venv\Scripts\python.exe" (
  echo Setting up for the first time...
  %PY% -m venv venv || (echo Failed to create venv & pause & exit /b 1)
)
"venv\Scripts\python.exe" -c "import flask" >nul 2>nul
if errorlevel 1 (
  echo Installing requirements...
  "venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo pip install failed & pause & exit /b 1)
)

rem --- open the browser after a short delay, then start the app ---
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"
echo Starting ButcherBridge at http://127.0.0.1:5000  (close this window to stop)
"venv\Scripts\python.exe" app.py
pause