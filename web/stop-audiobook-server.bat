@echo off
echo Stopping Audiobook Maker Server...
powershell -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -match 'uvicorn app:app' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Stopped!
pause
