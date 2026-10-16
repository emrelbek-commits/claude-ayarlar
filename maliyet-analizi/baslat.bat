@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python bulunamadi. https://www.python.org/downloads/ adresinden kurun ve kurulumda "Add Python to PATH" kutusunu isaretleyin.
  pause
  exit /b 1
)
if not exist .venv (
  echo Ilk kurulum yapiliyor, birkac dakika surebilir...
  python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m streamlit run app.py
pause
