@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    python LeaderboardClient.py
) else (
    py -3 LeaderboardClient.py
)
if errorlevel 1 pause
