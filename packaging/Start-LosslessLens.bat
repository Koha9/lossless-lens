@echo off
cd /d "%~dp0"
LosslessLens.exe %*
if errorlevel 1 pause
