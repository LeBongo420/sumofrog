@echo off
rem Shared start-up for the top-level .bat files. Lives in the files folder; you don't run it yourself.
cd /d "%~dp0"
rem Updating from an older flat folder: the wallet and payout file used to sit next to the .bat files,
rem one folder up from here. Move them in, never overwriting anything and never copying.
rem Step 1: if a copy exists in BOTH places, stop before moving anything.
if exist "%~dp0..\sumo-devnet-key.json" if exist "%~dp0sumo-devnet-key.json" goto two_wallets
if exist "%~dp0..\payout-address.txt" if exist "%~dp0payout-address.txt" goto two_payouts
rem Step 2: move each one in (only when the files folder doesn't have it yet), then check it really moved.
if exist "%~dp0..\sumo-devnet-key.json" move "%~dp0..\sumo-devnet-key.json" "%~dp0" >nul 2>nul
if exist "%~dp0..\sumo-devnet-key.json" goto wallet_move_failed
if exist "%~dp0..\payout-address.txt" move "%~dp0..\payout-address.txt" "%~dp0" >nul 2>nul
if exist "%~dp0..\payout-address.txt" goto payout_move_failed
call "%~dp0_setup.bat"
if errorlevel 1 exit /b 1
exit /b 0

:two_wallets
echo.
echo  !! TWO WALLETS FOUND. No wallet was moved or made.
echo  A wallet file called sumo-devnet-key.json is next to the buttons,
echo  and another one is in the files folder.
echo  DON'T DELETE sumo-devnet-key.json: each one may hold your test SUMO.
echo  To carry on, keep the wallet you want in the files folder and put the other
echo  one somewhere safe, for example a folder called old wallet. Then try again.
exit /b 2

:wallet_move_failed
echo.
echo  !! THE WALLET COULD NOT BE MOVED. No wallet was moved or made.
echo  The wallet file sumo-devnet-key.json is still next to the buttons.
echo  DON'T DELETE sumo-devnet-key.json: it holds your test SUMO.
echo  To carry on, MOVE it (do not copy) into the files folder yourself, for example by
echo  cutting and pasting it. A copy left next to the buttons would make the miner stop
echo  again with Two wallets found. Then try again.
exit /b 2

:two_payouts
echo.
echo  !! TWO PAYOUT FILES FOUND. No wallet was moved or made.
echo  A file called payout-address.txt is next to the buttons,
echo  and another one is in the files folder.
echo  Keep the one you want in the files folder and put the other somewhere safe.
echo  Then try again.
exit /b 2

:payout_move_failed
echo.
echo  !! THE PAYOUT FILE COULD NOT BE MOVED. No new wallet was made.
echo  The file payout-address.txt is still next to the buttons.
echo  To carry on, MOVE it (do not copy) into the files folder yourself, for example by
echo  cutting and pasting it. A copy left next to the buttons would make the miner stop
echo  again with Two payout files found. Then try again.
exit /b 2
