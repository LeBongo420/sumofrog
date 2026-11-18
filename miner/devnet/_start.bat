@echo off
rem Shared start-up for the top-level .bat files. Lives in the files folder; you don't run it yourself.
cd /d "%~dp0"
rem Updating from an older, flat folder: the wallet and payout file used to sit next to the .bat files
rem (one folder up from here). Move them in, never overwriting anything.
if exist "%~dp0..\sumo-devnet-key.json" if not exist "%~dp0sumo-devnet-key.json" move "%~dp0..\sumo-devnet-key.json" "%~dp0" >nul
if exist "%~dp0..\payout-address.txt" if not exist "%~dp0payout-address.txt" move "%~dp0..\payout-address.txt" "%~dp0" >nul
call "%~dp0_setup.bat"
if errorlevel 1 exit /b 1
exit /b 0
