@echo off
title Audiobook Maker Server
cd /d "A:\Cowork\audiobooks\web"
set "PATH=C:\Users\Owner\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin;%PATH%"
echo.
echo  Audiobook Maker is starting...
echo  On this PC:      http://localhost:8765
echo  On your phone:   http://100.69.165.27:8765   (via Tailscale, anywhere)
echo.
echo  (Port 8765 - leaves 8000 free for SportsSphere/Docker.)
echo  Keep this window open. Close it to stop the server.
echo.
"A:\Cowork\audiobooks\.venv\Scripts\python.exe" -m uvicorn app:app --host 0.0.0.0 --port 8765
pause
