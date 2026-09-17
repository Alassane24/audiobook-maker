@echo off
REM  Audiobook Maker server launcher.
REM
REM  Every machine-specific value lives in `local.env` at the repo root, which is
REM  gitignored. See local.env.example for the keys. With no local.env at all this
REM  falls back to a self-contained checkout on loopback, which is the portable
REM  default `web\paths.py` uses too.

title Audiobook Maker Server
setlocal EnableDelayedExpansion

REM  Repo root is the parent of this script's directory.
set "WEBDIR=%~dp0"
set "WEBDIR=%WEBDIR:~0,-1%"
for %%I in ("%WEBDIR%\..") do set "REPO=%%~fI"

REM  Defaults, overridden by local.env below.
set "AUDIOBOOK_HOST=127.0.0.1"
set "AUDIOBOOK_PORT=8765"
set "AUDIOBOOK_PYTHON=%REPO%\.venv\Scripts\python.exe"
set "AUDIOBOOK_FFMPEG_DIR="

if exist "%REPO%\local.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%REPO%\local.env") do (
    set "K=%%A"
    set "V=%%B"
    if not "!V!"=="" set "!K: =!=!V!"
  )
)

cd /d "%WEBDIR%"
if not "%AUDIOBOOK_FFMPEG_DIR%"=="" set "PATH=%AUDIOBOOK_FFMPEG_DIR%;%PATH%"

echo.
echo  Audiobook Maker is starting...
echo  On this PC / phone:  http://%AUDIOBOOK_HOST%:%AUDIOBOOK_PORT%
echo.
echo  Keep this window open. Close it to stop the server.
echo.
"%AUDIOBOOK_PYTHON%" -m uvicorn app:app --host %AUDIOBOOK_HOST% --port %AUDIOBOOK_PORT%
pause
