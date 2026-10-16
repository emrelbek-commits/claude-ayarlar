@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Maliyet Analizi

rem Kurulum daha once yapildiysa dogrudan ac
if exist ".venv\Scripts\python.exe" goto calistir

rem ---------- Python'u bul ----------
set "PY="
set "PYYOL=%LocalAppData%\Programs\Python\Python312\python.exe"
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto venv
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto venv
if exist "%PYYOL%" set "PY="%PYYOL%""
if defined PY goto venv

rem ---------- Python yoksa kur ----------
echo.
echo Python bulunamadi. Python 3.12 kuruluyor, birkac dakika surebilir...
echo (Yonetici izni gerekmez, sadece bu kullaniciya kurulur.)
echo.
where winget >nul 2>nul
if not errorlevel 1 (
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
)
if exist "%PYYOL%" goto pythonhazir

echo winget ile kurulamadi, python.org'dan indiriliyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile \"$env:TEMP\python-kurulum.exe\""
if not exist "%TEMP%\python-kurulum.exe" goto kurulumhatasi
"%TEMP%\python-kurulum.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%TEMP%\python-kurulum.exe" >nul 2>nul
if not exist "%PYYOL%" goto kurulumhatasi

:pythonhazir
set "PY="%PYYOL%""
echo Python kuruldu.

rem ---------- Uygulama ortamini kur ----------
:venv
echo.
echo Ilk kurulum yapiliyor (gerekli paketler indiriliyor)...
%PY% -m venv .venv
if errorlevel 1 goto kurulumhatasi
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto kurulumhatasi
echo Kurulum tamamlandi.

:calistir
echo.
echo Maliyet Analizi aciliyor. Kapatmak icin bu pencereyi kapatin.
".venv\Scripts\python.exe" -m streamlit run app.py
pause
exit /b 0

:kurulumhatasi
echo.
echo Kurulum tamamlanamadi. Internet baglantisini kontrol edip tekrar deneyin.
echo Olmazsa Python'u elle kurun: https://www.python.org/downloads/
echo (Kurulumda "Add Python to PATH" kutusunu isaretleyin, sonra bu dosyayi tekrar calistirin.)
if exist .venv rmdir /s /q .venv
pause
exit /b 1
