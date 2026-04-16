@echo off
start "" /min cmd /c "timeout /t 8 /nobreak >nul && start "" http://localhost:5000"
cmd /k "cd /d D:\Chatman_Retrieval && call retrieval_env\Scripts\activate.bat && python app/app.py"
