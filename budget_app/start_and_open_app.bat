@echo off
echo Starting Budget App...

REM Always run from the folder that contains app.py
cd /d "C:\Users\garre\OneDrive\Desktop\budget_app_repository\budget_app"

REM Activate virtual environment (Windows)
call venv\Scripts\activate.bat

REM ================================
REM Flask environment configuration
REM ================================
REM These are used by: flask db init/migrate/upgrade
set FLASK_APP=app.py
set FLASK_ENV=development

REM Open browser (non-blocking)
start http://127.0.0.1:5000/

REM Start the Flask app (this blocks until you stop the server)
python app.py

pause
