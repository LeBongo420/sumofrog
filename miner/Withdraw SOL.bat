@echo off
title Sumo Frog withdraw test SOL
cd /d "%~dp0"
call "%~dp0_setup.bat"
if errorlevel 1 goto done
echo.
echo  SEND THE MINER'S LEFTOVER TEST SOL TO YOUR OWN WALLET
echo  -----------------------------------------------------
echo  Paste your wallet's PUBLIC address (the one you'd share to receive coins),
echo  or just press Enter to use your saved payout address.
echo  NEVER paste a seed phrase or private key here or anywhere else.
echo  You'll see the amount and the address, and nothing is sent until you type  y
echo.
set "ADDR="
set /p "ADDR=Address (Enter = payout address): "
if defined ADDR (
  "%PY%" sumo_miner.py withdraw "%ADDR%"
) else (
  "%PY%" sumo_miner.py withdraw
)
:done
echo.
pause
