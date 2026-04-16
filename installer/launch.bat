@echo off
setlocal
:: Self-locating launcher.
:: Runs from wherever the app folder lives (thumb drive, D:\, etc.)
:: Uses the embedded Python that lives in the same folder.

set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

:: Keep the AI model cache inside the app folder
set "HF_HOME=%APP_DIR%\model_cache"
set "TRANSFORMERS_CACHE=%APP_DIR%\model_cache"

:: Prevent Intel OpenMP duplicate-DLL crash (safe to set unconditionally)
set "KMP_DUPLICATE_LIB_OK=TRUE"
set "KMP_INIT_AT_FORK=FALSE"
set "OMP_NUM_THREADS=1"

title Chatman Retrieval

echo ================================================
echo   Chatman Retrieval
echo   http://localhost:5000
echo.
echo   Your browser will open automatically.
echo   Close this window to stop the app.
echo ================================================
echo.

:: Open browser after Flask has had time to bind
start "" /min cmd /c "timeout /t 7 /nobreak >nul && start http://localhost:5000"

"%APP_DIR%\python\python.exe" "%APP_DIR%\run.py"

if %ERRORLEVEL% neq 0 (
    echo.
    echo   App exited unexpectedly. See error above.
    pause
)
