@echo off
title SUMO FROG MINER - test coins only
cd /d "%~dp0files"
call "%~dp0files\_start.bat"
if errorlevel 2 goto stopsafe
if errorlevel 1 goto fail

if exist "%~dp0files\sumo-devnet-key.json" goto mine
rem Never make a new wallet while an old one still sits next to the buttons.
if exist "%~dp0sumo-devnet-key.json" goto stopsafe
echo No test wallet yet, making one (test coins only, no real money)...
"%PY%" sumo_miner.py new-key
if errorlevel 1 goto fail
echo Getting free test SOL for fees...
"%PY%" sumo_miner.py faucet

:mine
echo.
echo  >^> MINING... close this window or press Ctrl+C to stop.
echo  (Window too small for the frog? Make it wider: about 100 columns.)
"%PY%" sumo_miner.py mine
if errorlevel 1 goto fail
pause
exit /b 0

:fail
echo.
echo Something went wrong (see the message above).
echo If it says you need test SOL, double-click "Get test SOL.bat", wait for it, then try again.
pause
exit /b 1

:stopsafe
echo.
echo Stopped on purpose. No new wallet was made.
echo If it says Two wallets found above, do not delete sumo-devnet-key.json. It holds your test SUMO.
pause
exit /b 2
