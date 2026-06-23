@echo off
REM AutoGitPull_Daily 스케줄러가 호출. 실제 동기화 로직은 auto_pull.ps1 (patch백업+reset+로그).
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\user\Antigravity_Market_Dashboard\scripts\auto_pull.ps1"
