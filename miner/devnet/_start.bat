@echo off
rem Shared start-up for the top-level .bat files. Lives in the files folder; you don't run it yourself.
cd /d "%~dp0"
rem Updating from an older flat folder: the wallet and payout file used to sit next to the .bat files,
rem one folder up from here. Move them in, never overwriting anything and never copying.
if exist "%~dp0..\sumo-devnet-key.json" if not exist "%~dp0sumo-devnet-key.json" move "%~dp0..\sumo-devnet-key.json" "%~dp0" >nul 2>nul
if exist "%~dp0..\payout-address.txt" if not exist "%~dp0payout-address.txt" move "%~dp0..\payout-address.txt" "%~dp0" >nul 2>nul
rem If either file is STILL next to the buttons, two copies exist or the move failed. Stop, change nothing.
if exist "%~dp0..\sumo-devnet-key.json" goto two_wallets
if exist "%~dp0..\payout-address.txt" goto two_payouts
call "%~dp0_setup.bat"
if errorlevel 1 exit /b 1
exit /b 0

:two_wallets
echo.
echo  !! TWO WALLETS FOUND, OR THE WALLET COULD NOT BE MOVED. Nothing was changed.
echo  A wallet file called sumo-devnet-key.json is still next to the buttons.
echo  Another one may also be in the files folder.
echo  DON'T DELETE sumo-devnet-key.json: it holds your test SUMO.
echo  To carry on, keep the wallet you want in the files folder and put the other
echo  one somewhere safe, for example a folder called old wallet. Then try again.
echo  No new wallet has been made.
exit /b 2

:two_payouts
echo.
echo  !! TWO PAYOUT FILES FOUND, OR THE FILE COULD NOT BE MOVED. Nothing was changed.
echo  A file called payout-address.txt is still next to the buttons.
echo  Another one may also be in the files folder.
echo  Keep the one you want in the files folder and put the other somewhere safe.
echo  Then try again. No new wallet has been made.
exit /b 2
