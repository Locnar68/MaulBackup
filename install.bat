@echo off
REM ===============================================================
REM  MichaelMaul Backup - one-time setup.
REM  Double-click this once. It installs everything, asks a few
REM  questions, runs the Google sign-in, and makes the Desktop button.
REM  Safe to run again later - it updates instead of duplicating.
REM ===============================================================
cd /d "%~dp0"
python install.py
if %errorlevel% neq 0 (
  echo.
  echo Could not run install.py with 'python'.
  echo Make sure Python is installed from python.org and that
  echo "Add Python to PATH" was checked during installation.
  echo.
  pause
)
