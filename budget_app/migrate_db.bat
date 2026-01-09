@echo off
echo Running database migration...

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
REM Prompt for migration message
REM ------------------------------------------------
echo.
set /p MIGRATION_MSG=Enter migration description: 
echo.

REM Safety check: empty message
if "%MIGRATION_MSG%"=="" (
  echo ERROR: Migration description cannot be empty.
  goto end
)

REM ------------------------------------------------
REM Run migration
REM ------------------------------------------------
flask db migrate -m "%MIGRATION_MSG%"

:end
pause
