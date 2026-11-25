@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or newer, then reopen this window.
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js and npm were not found. Install Node.js, then reopen this window.
  pause
  exit /b 1
)

if not exist "backend\.venv\Scripts\python.exe" python -m venv backend\.venv
if errorlevel 1 (
  echo Could not create a Python environment. Check that Python is installed and available on PATH.
  pause
  exit /b 1
)
call backend\.venv\Scripts\activate.bat
python -m pip install -r backend\requirements.txt
if errorlevel 1 goto failed

if not exist "frontend\node_modules" call npm --prefix frontend install
if errorlevel 1 goto failed
call npm --prefix frontend run build
if errorlevel 1 goto failed

if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul
findstr /C:"GROQ_API_KEY=your_groq_api_key" "backend\.env" >nul
if not errorlevel 1 (
  echo Add your Groq API key to backend\.env, save it, and run this file again.
  start "" notepad "backend\.env"
  pause
  exit /b 1
)

start "" "http://127.0.0.1:8000"
python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
goto end

:failed
echo Setup failed. Read the error above, fix it, then run this file again.
pause
:end
endlocal

