@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Music Intelligence - Start Everything
echo ============================================
echo.

if not exist ".env" (
    echo ERROR: .env not found in %cd%
    pause
    exit /b 1
)

echo [1/3] Importing playlists...
echo       (A browser window will open for Spotify login if needed.
echo        Log in and click Agree promptly -- it can time out if left idle.)
python -m backend.cli import-playlists
echo.

echo [2/3] Starting backend server in a new window...
start "Music Intelligence - Backend" cmd /k "cd /d %~dp0 && python -m backend.cli serve"

echo       Waiting a few seconds for the backend to come up...
timeout /t 5 /nobreak >nul

echo [3/3] Starting frontend in a new window...
start "Music Intelligence - Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ============================================
echo  Backend and frontend are starting in their
echo  own windows. Give it ~10 seconds, then open:
echo    http://localhost:5173
echo ========================================