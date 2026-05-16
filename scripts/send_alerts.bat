@echo off
setlocal

cd /d C:\Users\Vitor-Pessoal\Desktop\projetoV1

call venv\Scripts\activate.bat

set FLASK_APP=run.py
set APP_ENV=development

if not exist logs mkdir logs

for /f "tokens=1-3 delims=/" %%a in ("%date%") do (
  set d=%%c-%%b-%%a
)

for /f "tokens=1-2 delims=:" %%a in ("%time%") do (
  set t=%%a%%b
)

python -m flask send-alerts >> logs\send_alerts_%d%_%t%.log 2>&1
