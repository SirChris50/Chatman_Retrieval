@echo off
setlocal enabledelayedexpansion
title Chatman Retrieval -- Build Installer

:: ─────────────────────────────────────────────────────────────
::  build.bat
::
::  Produces ChatmanRetrieval_Setup\ -- a fully self-contained
::  installer that works completely offline on family PCs.
::
::  The heavy work (downloading Python, pip install) only runs
::  once; results are cached in build_cache\ so rebuilds are fast.
::
::  Layout of ChatmanRetrieval_Setup\ when done:
::    INSTALL.bat       simple copy + shortcut script
::    python\           embeddable Python with ALL packages pre-installed
::    app_files\        application source, data, launcher
::      app\
::      templates\
::      data\
::      static\
::      model_cache\    (if present -- saves first-launch download)
::      run.py
::      requirements.txt
::      launch.bat
:: ─────────────────────────────────────────────────────────────

set "PROJECT=%~dp0"
if "!PROJECT:~-1!"=="\" set "PROJECT=!PROJECT:~0,-1!"

set "CACHE_DIR=!PROJECT!\build_cache"
set "OUTPUT=!PROJECT!\ChatmanRetrieval_Setup"

set "PY_VER=3.11.9"
set "PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
set "PIP_URL=https://bootstrap.pypa.io/get-pip.py"

set "PY_ZIP=!CACHE_DIR!\python-embed.zip"
set "PIP_PY=!CACHE_DIR!\get-pip.py"
set "PY_ENV=!CACHE_DIR!\python"

echo.
echo ============================================================
echo   Chatman Retrieval -- Build Installer
echo ============================================================
echo.

:: ── Step 1: Python environment ────────────────────────────────
if exist "!PY_ENV!\python.exe" (
    echo [1/5] Python environment found in build_cache\.
    set /p "REUSE=        Reuse it? Saves ~20 min of pip install. (Y/n): "
    if /i "!REUSE!"=="n" (
        echo        Rebuilding Python environment...
        rmdir /s /q "!PY_ENV!"
        goto :build_python
    )
    echo        Reusing cached environment.
    goto :copy_python
)

:build_python
echo [1/5] Building Python environment (runs once, ~20-30 min^)...
echo.

if not exist "!CACHE_DIR!" mkdir "!CACHE_DIR!"

:: Download Python embeddable zip
if not exist "!PY_ZIP!" (
    echo        Downloading Python !PY_VER! embeddable (~8 MB^)...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '!PY_URL!' -OutFile '!PY_ZIP!'"
    if errorlevel 1 (
        echo  ERROR: Could not download Python embeddable zip.
        pause & exit /b 1
    )
)

:: Extract
echo        Extracting Python...
mkdir "!PY_ENV!"
powershell -NoProfile -Command "Expand-Archive -Path '!PY_ZIP!' -DestinationPath '!PY_ENV!' -Force"
if errorlevel 1 (
    echo  ERROR: Could not extract Python.
    pause & exit /b 1
)

:: Patch .pth file to enable site-packages (required for pip to work)
echo        Patching .pth file...
for %%f in ("!PY_ENV!\python*._pth") do (
    powershell -NoProfile -Command ^
        "(Get-Content '%%f') -replace '^#import site', 'import site' | Set-Content '%%f'"
)

:: Download and run get-pip.py
if not exist "!PIP_PY!" (
    echo        Downloading get-pip.py...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '!PIP_URL!' -OutFile '!PIP_PY!'"
    if errorlevel 1 (
        echo  ERROR: Could not download get-pip.py.
        pause & exit /b 1
    )
)
echo        Installing pip into embedded Python...
"!PY_ENV!\python.exe" "!PIP_PY!" --no-warn-script-location --quiet
if errorlevel 1 (
    echo  ERROR: pip installation failed.
    pause & exit /b 1
)

:: Install all packages (the slow part -- downloads torch etc.)
echo.
echo        Installing packages (Flask, torch, sentence-transformers,
echo        chromadb, rapidfuzz -- may take 20-30 min^)...
echo        Download progress will appear below:
echo.
"!PY_ENV!\python.exe" -m pip install ^
    -r "!PROJECT!\requirements.txt" ^
    --no-warn-script-location
if errorlevel 1 (
    echo.
    echo  ERROR: Package installation failed.
    echo  Check your internet connection and run build.bat again.
    echo  The partially-built environment in build_cache\ will be reused
    echo  and pip will only re-download what is missing.
    pause & exit /b 1
)
echo.
echo        Python environment ready.

:: ── Step 2: Copy Python environment to output ─────────────────
:copy_python
echo.
echo [2/5] Assembling installer package...

if exist "!OUTPUT!" rmdir /s /q "!OUTPUT!"
mkdir "!OUTPUT!"
mkdir "!OUTPUT!\app_files"

echo        Copying Python environment (~may take a minute^)...
xcopy /e /y /i /q "!PY_ENV!" "!OUTPUT!\python\" >nul
echo        Done.

:: ── Step 3: Copy application files ───────────────────────────
echo.
echo [3/5] Copying application files...
xcopy /e /y /i /q "!PROJECT!\app"         "!OUTPUT!\app_files\app\"       >nul
xcopy /e /y /i /q "!PROJECT!\templates"   "!OUTPUT!\app_files\templates\" >nul
xcopy /e /y /i /q "!PROJECT!\data"        "!OUTPUT!\app_files\data\"      >nul
copy  /y "!PROJECT!\run.py"                   "!OUTPUT!\app_files\run.py"           >nul
copy  /y "!PROJECT!\requirements.txt"         "!OUTPUT!\app_files\requirements.txt" >nul
copy  /y "!PROJECT!\installer\launch.bat"     "!OUTPUT!\app_files\launch.bat"       >nul
if exist "!PROJECT!\static" (
    xcopy /e /y /i /q "!PROJECT!\static"  "!OUTPUT!\app_files\static\" >nul
)
echo        Done.

:: ── Step 4: Bundle model cache ─────────────────────────────────
echo.
echo [4/5] Checking model cache...
if exist "!PROJECT!\model_cache" (
    echo        Bundling model_cache -- family members won't need to
    echo        download the AI model on first launch.
    xcopy /e /y /i /q "!PROJECT!\model_cache" "!OUTPUT!\app_files\model_cache\" >nul
    echo        Done.
) else (
    echo        model_cache not found.
    echo        The AI model will download on first launch (~90 MB^).
)

:: ── Step 5: Copy installer script ─────────────────────────────
echo.
echo [5/5] Copying INSTALL.bat...
copy /y "!PROJECT!\installer\INSTALL.bat" "!OUTPUT!\INSTALL.bat" >nul
echo        Done.

:: ── Summary ───────────────────────────────────────────────────
echo.
echo ============================================================
echo   BUILD COMPLETE
echo.
echo   Installer package: !OUTPUT!
echo.
echo   To distribute to family members:
echo     1. Right-click ChatmanRetrieval_Setup\
echo        ^> "Send to ^> Compressed (zipped) folder"
echo     2. Share the zip (will be large -- Python + torch ~2-3 GB)
echo     3. They extract it and double-click INSTALL.bat
echo     4. No internet required on their machine.
echo     5. A "Chatman Retrieval" shortcut appears on
echo        their Desktop when done.
echo.
echo   To rebuild quickly next time (app changes only^):
echo     Just run build.bat again -- Python environment is cached
echo     in build_cache\ and will be reused automatically.
echo ============================================================
echo.
pause
