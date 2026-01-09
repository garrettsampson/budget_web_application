@echo off
echo Applying database migrations...

REM ------------------------------------------------
REM Go to folder that contains app.py
REM ------------------------------------------------
cd /d "C:\Users\garre\OneDrive\Desktop\budget_app_repository\budget_app"

REM ------------------------------------------------
REM Activate virtual environment
REM ------------------------------------------------
call venv\Scripts\activate.bat

REM ------------------------------------------------
REM Flask CLI environment variables
REM ------------------------------------------------
set FLASK_APP=app.py
set FLASK_ENV=development

REM ------------------------------------------------
REM Apply migration
REM ------------------------------------------------
flask db upgrade

pause
