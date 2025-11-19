@echo off
echo Starting Budget App...

cd /d "C:\Users\garre\OneDrive\Desktop\budget_app_repository\budget_app"

call venv\Scripts\activate.bat

start http://127.0.0.1:5000/

python app.py

pause
