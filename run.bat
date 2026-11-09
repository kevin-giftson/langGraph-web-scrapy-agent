@echo off
cd /d "%~dp0"
if not exist .venv (
  uv venv .venv --python 3.13
  uv pip install --python .venv\Scripts\python.exe -r requirements.txt
  .venv\Scripts\python.exe -m playwright install chromium
)
if not exist .env copy .env.example .env
.venv\Scripts\python.exe -X utf8 app.py
