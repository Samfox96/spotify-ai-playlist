@echo off
setlocal

rem Always run from the folder this script lives in, regardless of where
rem it's double-clicked from.
cd /d "%~dp0"

echo ============================================
echo  Music Intelligence - Full Pipeline
echo ============================================
echo.

if not exist ".env" (
    echo ERROR: .env not found in %cd%
    echo Copy your .env file into this project folder before running this script.
    echo.
    pause
    exit /b 1
)

rem Drag-and-drop a folder onto this script to override the export path.
rem Otherwise it falls back to the default below -- edit this line if your
rem export lives somewhere else.
set EXPORT_PATH=%~1
if "%EXPORT_PATH%"=="" (
    set "EXPORT_PATH=C:\Users\samue\OneDrive\Documents\Projects\music intelligence\backend\Spotify Extended Streaming History"
)

echo Using export folder:
echo   %EXPORT_PATH%
echo.

echo [1/4] Importing streaming history...
python -m backend.cli import-history --export "%EXPORT_PATH%"
echo.

echo [2/4] Enriching discovered tracks with full metadata...
echo       (If this fails with a 403 error, that's Spotify's Extended Quota
echo        Mode restriction, not a bug -- it'll start working once Spotify
echo        approves the request. Safe to ignore for now.)
python -m backend.cli enrich-tracks
echo.

echo [3/4] Fetching artist genres...
echo       (Same 403 caveat as above may apply here too.)
python -m backend.cli import-artists
echo.

echo [4/4] Final stats:
python -m backend.cli stats

echo.
echo ============================================
echo  Done.
echo ============================================
pause