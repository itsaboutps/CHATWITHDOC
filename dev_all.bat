@echo off
REM Unified Windows dev launcher for backend + frontend
REM Usage:
REM   dev_all.bat
REM   set BACKEND_PORT=8010 && dev_all.bat
REM   dev_all.bat check

setlocal ENABLEDELAYEDEXPANSION

if "%1"=="check" (
  echo Configuration:
  echo   BACKEND_PORT=%BACKEND_PORT%
  echo   BACKEND_HOST=%BACKEND_HOST%
  echo   FRONTEND_PORT=%FRONTEND_PORT%
  goto :eof
)

if "%BACKEND_PORT%"=="" set BACKEND_PORT=8000
if "%BACKEND_HOST%"=="" set BACKEND_HOST=127.0.0.1
if "%FRONTEND_PORT%"=="" set FRONTEND_PORT=3000
if "%VENV_DIR%"=="" set VENV_DIR=.venv

echo [dev_all] Preparing Python virtual environment (%VENV_DIR%)
if not exist %VENV_DIR% ( python -m venv %VENV_DIR% )
call %VENV_DIR%\Scripts\activate.bat

echo [dev_all] Installing backend dependencies (idempotent)
python -m pip install --upgrade pip >NUL 2>&1
pip install -r backend\requirements.txt >NUL 2>&1

set USE_IN_MEMORY=true
set NEXT_PUBLIC_BACKEND_URL=http://%BACKEND_HOST%:%BACKEND_PORT%

REM Start backend in a new window
echo [dev_all] Starting backend on %BACKEND_HOST%:%BACKEND_PORT%
start "RAG Backend" cmd /c "cd backend && uvicorn app.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% --reload"

REM Frontend
cd frontend
if not exist .env.local (
  echo NEXT_PUBLIC_BACKEND_URL=%NEXT_PUBLIC_BACKEND_URL%>.env.local
)
if not exist node_modules (
  echo [dev_all] Installing npm dependencies
  call npm install
)
echo [dev_all] Starting frontend dev server on http://localhost:%FRONTEND_PORT%
set PORT=%FRONTEND_PORT%
call npm run dev

REM On exit user can close backend window manually or:
echo To stop backend close the "RAG Backend" window or use: taskkill /FI "WINDOWTITLE eq RAG Backend*"
endlocal
