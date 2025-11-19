@echo off
echo Starting Budget App...

REM Activate the virtual environment
call venv\Scripts\activate

start http://127.0.0.1:5000/
python app.py


pause
