@echo off
title Sumo Frog payout address
cd /d "%~dp0files"
call "%~dp0files\_start.bat"
if errorlevel 1 goto done
echo.
echo  SEND REWARDS TO YOUR OWN WALLET
echo  -------------------------------
echo  Paste your wallet's PUBLIC address (the one you'd share to receive coins).
echo  NEVER paste a seed phrase or private key here or anywhere else.
echo  Type  none  to keep rewards in the miner's own test wallet.
echo.
set "ADDR="
set /p "ADDR=Address: "
if not defined ADDR goto done
"%PY%" sumo_miner.py set-payout "%ADDR%"
:done
echo.
pause
