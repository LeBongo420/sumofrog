@echo off
title Sumo Frog balance
cd /d "%~dp0"
call "%~dp0_setup.bat"
if errorlevel 1 goto done
"%PY%" sumo_miner.py balance
"%PY%" sumo_miner.py status
:done
echo.
pause
