@echo off
rem Shared setup for the Sumo Frog .bat files. Finds Python, makes .venv once, installs solders once.
rem Sets PY to the venv's python.exe. Called by the other .bat files; you don't need to run it.
cd /d "%~dp0"
chcp 65001 >nul 2>nul
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%PY%" goto have_venv

echo First run: setting up the miner. This takes a minute and only happens once.
set "BASE="
py -3 -c "import sys" >nul 2>nul && set "BASE=py -3"
if defined BASE goto make_venv
python -c "import sys" >nul 2>nul && set "BASE=python"
if defined BASE goto make_venv
echo.
echo Python isn't installed yet.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
echo then double-click this file again.
exit /b 1

:make_venv
%BASE% -m venv "%~dp0.venv"
if errorlevel 1 (
  echo Couldn't create the .venv folder.
  exit /b 1
)

:have_venv
"%PY%" -c "import solders" >nul 2>nul
if not errorlevel 1 exit /b 0
echo Installing the one thing the miner needs (solders)...
"%PY%" -m pip install --disable-pip-version-check -q -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo Install failed. Check your internet connection and try again.
  exit /b 1
)
exit /b 0
