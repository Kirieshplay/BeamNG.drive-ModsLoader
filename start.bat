@echo off
setlocal
cd /d "%~dp0"
set "PYW="
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe" set "PYW=%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe"
if not defined PYW if exist "%~dp0runtime\pythonw.exe" set "PYW=%~dp0runtime\pythonw.exe"
if not defined PYW where pythonw.exe >nul 2>nul && set "PYW=pythonw.exe"
if not defined PYW where pyw.exe >nul 2>nul && set "PYW=pyw.exe"
if not defined PYW (
    echo.
    echo  Python не найден. Установите Python 3.11 или новее и повторите запуск.
    echo.
    pause
    exit /b 1
)
start "" "%PYW%" "%~dp0main.py"
endlocal
