@echo off
setlocal enabledelayedexpansion
title Chatman Retrieval -- Setup

:: ─────────────────────────────────────────────────────────────
::  INSTALL.bat
::
::  Completely offline installer -- no internet required.
::  All packages and Python are pre-bundled by build.bat.
::
::  Runs in-place: the app runs directly from this folder.
::  Nothing is copied to C:\Users -- only a Desktop shortcut
::  is created there.
::
::  Expected layout next to this script:
::    python\        embeddable Python with all packages installed
::    app_files\     application source files
:: ─────────────────────────────────────────────────────────────

set "INSTALL_DIR=%~dp0"
if "!INSTALL_DIR:~-1!"=="\" set "INSTALL_DIR=!INSTALL_DIR:~0,-1!"

echo.
echo ============================================================
echo   Chatman Retrieval -- Setup
echo ============================================================
echo.
echo   App location: !INSTALL_DIR!
echo   (Runs directly from this folder -- nothing is copied to
echo    your C: drive except a Desktop shortcut.)
echo.

:: ── Verify bundle is intact ───────────────────────────────────
if not exist "!INSTALL_DIR!\python\python.exe" (
    echo  ERROR: python\ folder not found or incomplete.
    echo  Please re-download the full installer package.
    pause & exit /b 1
)
if not exist "!INSTALL_DIR!\app_files\run.py" (
    echo  ERROR: app_files\ folder not found or incomplete.
    echo  Please re-download the full installer package.
    pause & exit /b 1
)

:: ── Already set up? ───────────────────────────────────────────
if exist "!INSTALL_DIR!\run.py" (
    echo  This folder is already set up.
    echo.
    echo  Choose an option:
    echo    [U] Update app files -- re-copies app files from app_files\
    echo    [C] Cancel
    echo.
    set /p "CHOICE=  Your choice (U/C): "
    if /i "!CHOICE!"=="c" (
        echo  Cancelled.
        pause & exit /b 0
    )
    if /i "!CHOICE!"=="u" (
        echo.
        echo  Updating application files...
        goto :copy_app_files
    )
    echo  Invalid choice. Cancelled.
    pause & exit /b 0
)

:: ── Step 1: Unpack application files ──────────────────────────
:copy_app_files
echo [1/2] Unpacking application files...
xcopy /e /y /i /q "!INSTALL_DIR!\app_files\app"         "!INSTALL_DIR!\app\"       >nul
xcopy /e /y /i /q "!INSTALL_DIR!\app_files\templates"   "!INSTALL_DIR!\templates\" >nul
xcopy /e /y /i /q "!INSTALL_DIR!\app_files\data"        "!INSTALL_DIR!\data\"      >nul
copy  /y           "!INSTALL_DIR!\app_files\run.py"      "!INSTALL_DIR!\run.py"           >nul
copy  /y           "!INSTALL_DIR!\app_files\requirements.txt" "!INSTALL_DIR!\requirements.txt" >nul
copy  /y           "!INSTALL_DIR!\app_files\launch.bat"  "!INSTALL_DIR!\launch.bat"       >nul
if exist "!INSTALL_DIR!\app_files\static" (
    xcopy /e /y /i /q "!INSTALL_DIR!\app_files\static"  "!INSTALL_DIR!\static\" >nul
)
if exist "!INSTALL_DIR!\app_files\model_cache" (
    echo        Copying bundled model cache...
    xcopy /e /y /i /q "!INSTALL_DIR!\app_files\model_cache" "!INSTALL_DIR!\model_cache\" >nul
)
echo        Done.
echo.

:: ── Step 2: Desktop shortcut (.lnk) ───────────────────────────
echo [2/2] Creating desktop shortcut...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut([System.IO.Path]::Combine([System.Environment]::GetFolderPath('Desktop'), 'Chatman Retrieval.lnk')); $sc.TargetPath = '!INSTALL_DIR!\launch.bat'; $sc.WorkingDirectory = '!INSTALL_DIR!'; $sc.WindowStyle = 1; $sc.Description = 'Chatman Retrieval QA System'; $sc.Save()"
echo        Done.

echo.
echo ============================================================
echo   SETUP COMPLETE!
echo.
echo   "Chatman Retrieval" shortcut is on your Desktop.
echo   Double-click it to start.  No internet required.
echo.
echo   On first launch the app may take 30-60 seconds
echo   to load. Your browser opens automatically at
echo   http://localhost:5000
echo.
echo   To stop the app, close the console window.
echo ============================================================
echo.
pause
