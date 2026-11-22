@echo off
setlocal
title Eligius - Uni-Produktion

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\deploy-production.ps1" %*
set "deploy_exit=%errorlevel%"
echo.
if not "%deploy_exit%"=="0" echo Vorgang fehlgeschlagen. Details stehen oben. Fehlercode: %deploy_exit%
pause
exit /b %deploy_exit%
