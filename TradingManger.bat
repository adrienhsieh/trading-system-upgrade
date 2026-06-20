@echo off
title Trading_System_Console
color 0B

:menu
cls
echo ================================================
echo           TRADING SYSTEM CONTROL CENTER
echo ================================================
echo.
echo    [1] Start Services
echo    [2] Stop All Services
echo    [3] Restart Services
echo    [4] Status Check
echo    [5] Exit
echo.
echo ================================================
set /p choice=Select option (1-5): 

if "%choice%"=="1" goto start_all
if "%choice%"=="2" goto stop_all
if "%choice%"=="3" goto restart_all
if "%choice%"=="4" goto status
if "%choice%"=="5" exit
goto menu

:start_all
cls
color 0A
echo Starting services...
cd /d "%~dp0"
call :do_stop >nul 2>&1
timeout /t 1 /nobreak > nul
start "Trading_Server" cmd /k ".venv\Scripts\python.exe run.py"
echo.
echo OK: Services started! http://localhost:8787
echo.
pause
goto menu

:stop_all
cls
color 0C
echo Stopping services...
call :do_stop
echo.
pause
goto menu

:restart_all
cls
echo Restarting...
call :do_stop
timeout /t 2 /nobreak > nul
goto start_all

:status
cls
color 0E
echo ---- Port 8787 Status ------------------------------
netstat -ano | findstr ":8787" | findstr "LISTENING"
if %errorlevel% equ 0 (
    echo Flask is RUNNING on port 8787
) else (
    echo Flask is STOPPED
)
echo.
echo ---- Python Processes ------------------------------
tasklist /fi "imagename eq python.exe" 2>nul | findstr python
tasklist /fi "imagename eq pythonw.exe" 2>nul | findstr pythonw
echo.
pause
goto menu

:do_stop
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8787" ^| findstr "LISTENING"') do (
    echo Killing PID %%a on port 8787...
    taskkill /f /pid %%a >nul 2>&1
)
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1
echo OK: Services stopped.
exit /b
