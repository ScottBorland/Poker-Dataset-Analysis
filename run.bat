@echo off
REM Starts the FastAPI backend (port 8000) and the Vite web frontend (port 5173).
REM Run from anywhere - this script cd's to its own folder first.

cd /d "%~dp0"

if not exist "frontend\node_modules" (
    echo Installing frontend dependencies...
    pushd frontend
    call npm install
    popd
)

echo Starting FastAPI backend on http://127.0.0.1:8000 ...
start "Poker API" cmd /k python -m uvicorn src.api:app --reload --port 8000

echo Starting web frontend on http://localhost:5173 ...
start "Poker Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Both servers launching in separate windows. Open http://localhost:5173
