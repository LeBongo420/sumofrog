@echo off
title Sumo Frog balance
cd /d "%~dp0files"
call "%~dp0files\_start.bat"
if errorlevel 1 goto done
"%PY%" sumo_miner.py balance
"%PY%" sumo_miner.py status
:done
echo.
pause
