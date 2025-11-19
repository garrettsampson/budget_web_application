@echo off
echo Starting Budget App...

REM Activate the virtual environment
call venv\Scripts\activate

REM Run the Flask app
python app.py

pause
