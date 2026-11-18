@echo off
title SUMO FROG MINER - test coins only
rem One launcher with a numbered menu. Everything else lives in the files folder.
cd /d "%~dp0files"
rem Wallet safety first: _start.bat moves an old wallet in, or stops on two wallets. Exit code 2 = stop on purpose.
call "%~dp0files\_start.bat"
if errorlevel 2 goto stopsafe
if errorlevel 1 goto fail
rem An older miner folder can still hold the five old buttons and the old guide: warn once, before the menu.
set "OLDBTN="
if exist "%~dp0Mine SUMO.bat" set "OLDBTN=1"
if exist "%~dp0Check balance.bat" set "OLDBTN=1"
if exist "%~dp0Get test SOL.bat" set "OLDBTN=1"
if exist "%~dp0Set payout address.bat" set "OLDBTN=1"
if exist "%~dp0Withdraw SOL.bat" set "OLDBTN=1"
if exist "%~dp0HOW TO MINE.txt" set "OLDBTN=1"
if defined OLDBTN goto oldbuttons

:menu
cls
echo.
echo   SUMO FROG MINER   test coins only, no real money
echo   ------------------------------------------------
echo.
echo     1   Mine SUMO
echo     2   Check balance
echo     3   Get test SOL
echo     4   Set payout address
echo     5   Withdraw SOL
echo     6   Exit
echo.
choice /c 123456 /n /m "  Press a number from 1 to 6: "
if errorlevel 6 goto bye
if errorlevel 5 goto withdraw
if errorlevel 4 goto payout
if errorlevel 3 goto faucet
if errorlevel 2 goto balance
if errorlevel 1 goto mine
goto menu

:mine
rem Never make a new wallet while an old one still sits next to this launcher.
if exist "%~dp0files\sumo-devnet-key.json" goto do_mine
if exist "%~dp0sumo-devnet-key.json" goto stopsafe
cls
echo.
echo  No test wallet yet, making one. Test coins only, no real money.
"%PY%" sumo_miner.py new-key
if errorlevel 1 goto action_failed
echo  Getting free test SOL for fees...
"%PY%" sumo_miner.py faucet
:do_mine
echo.
echo  ^>^> MINING... close this window or press Ctrl+C to stop.
echo  Window too small for the frog? Make it wider, about 100 columns.
"%PY%" sumo_miner.py mine
if errorlevel 1 goto action_failed
echo.
echo  Mining stopped.
pause
goto menu

:balance
cls
"%PY%" sumo_miner.py balance
"%PY%" sumo_miner.py status
goto done

:faucet
cls
"%PY%" sumo_miner.py faucet
echo.
echo  The faucet allows one request every 10 minutes. Test SOL is worthless.
echo  On public devnet this often fails: use https://faucet.solana.com instead.
goto done

:payout
cls
echo.
echo  SEND REWARDS TO YOUR OWN WALLET
echo  -------------------------------
echo  Paste your wallet's PUBLIC address, the one you would share to receive coins.
echo  NEVER paste a seed phrase or private key here or anywhere else.
echo  Type  none  to keep rewards in the miner's own test wallet.
echo.
set "ADDR="
set /p "ADDR=Address: "
rem Strip any double quotes, so nothing typed can add extra options. The -- keeps it an address.
if defined ADDR set "ADDR=%ADDR:"=%"
if not defined ADDR goto menu
"%PY%" sumo_miner.py set-payout -- "%ADDR%"
goto done

:withdraw
cls
echo.
echo  SEND THE MINER'S LEFTOVER TEST SOL TO YOUR OWN WALLET
echo  -----------------------------------------------------
echo  Paste your wallet's PUBLIC address, the one you would share to receive coins,
echo  or just press Enter to use your saved payout address.
echo  NEVER paste a seed phrase or private key here or anywhere else.
echo  You will see the amount and the address, and nothing is sent until you type  y
echo.
set "ADDR="
set /p "ADDR=Address (Enter = payout address): "
if defined ADDR set "ADDR=%ADDR:"=%"
rem No ( ) blocks here: a folder name like "sumo (1)" would break them.
if defined ADDR goto withdraw_to
"%PY%" sumo_miner.py withdraw
goto done
:withdraw_to
"%PY%" sumo_miner.py withdraw -- "%ADDR%"
goto done

:done
echo.
pause
goto menu

:action_failed
echo.
echo  Something went wrong, see the message above.
echo  If it says you need test SOL, get some at https://faucet.solana.com, pick Devnet, then try again.
pause
goto menu

:fail
echo.
echo  Something went wrong, see the message above.
pause
exit /b 1

:stopsafe
echo.
echo  Stopped on purpose. No new wallet was made.
echo  If it says Two wallets found above, do not delete sumo-devnet-key.json. It holds your test SUMO.
pause
exit /b 2

:oldbuttons
cls
echo.
echo  !! OLD FILES FOUND next to SUMO Frog.bat.
echo  Please delete the five old buttons. They are from the older miner and are no longer used:
echo      Mine SUMO.bat
echo      Check balance.bat
echo      Get test SOL.bat
echo      Set payout address.bat
echo      Withdraw SOL.bat
echo  The old Mine SUMO.bat can make a SECOND wallet. Use SUMO Frog.bat only.
echo  If HOW TO MINE.txt sits next to SUMO Frog.bat, that is the OLD guide. Delete it too.
echo  The current guide is in the files folder.
echo  Delete only those five .bat files and that old HOW TO MINE.txt.
echo  NEVER delete sumo-devnet-key.json. It is your wallet and it holds your test SUMO.
echo.
pause
goto menu

:bye
exit /b 0
