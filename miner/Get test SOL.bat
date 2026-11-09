@echo off
title Sumo Frog test SOL
cd /d "%~dp0"
call "%~dp0_setup.bat"
if errorlevel 1 goto done
"%PY%" sumo_miner.py faucet
:done
echo.
echo (The faucet allows one request every 10 minutes. Test SOL is worthless.)
pause
