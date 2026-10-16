@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Maliyet Analizi

rem Zip'in icinden calistirilirsa Windows dosyalari gecici klasore acar; kurulum orada calismaz.
echo "%~dp0" | findstr /i /c:"\Temp\" | findstr /i /c:".zip" >nul
if not errorlevel 1 goto zipten

rem Paket ortami kisa bir yolda tutulur (uzun klasor yollarinda kurulum hatasini onler)
set "VENV=%LocalAppData%\MaliyetAnalizi\venv"
set "VPY=%VENV%\Scripts\python.exe"
rem Veriler Belgeler klasorunde tutulur; uygulamanin yeni surumunu indirmek verileri etkilemez
set "MALIYET_VERI=%USERPROFILE%\Documents\MaliyetAnalizi"

rem Kurulum daha once yapildiysa dogrudan ac
if exist "%VPY%" goto calistir

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
if exist "%VENV%" rmdir /s /q "%VENV%"
%PY% -m venv "%VENV%"
if errorlevel 1 goto kurulumhatasi
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto kurulumhatasi
echo Kurulum tamamlandi.

:calistir
echo.
echo Maliyet Analizi aciliyor. Veriler: %MALIYET_VERI%
echo Kapatmak icin bu pencereyi kapatin.
"%VPY%" -m streamlit run app.py
pause
exit /b 0

:kurulumhatasi
echo.
echo Kurulum tamamlanamadi. Internet baglantisini kontrol edip tekrar deneyin.
echo Olmazsa Python'u elle kurun: https://www.python.org/downloads/
echo (Kurulumda "Add Python to PATH" kutusunu isaretleyin, sonra bu dosyayi tekrar calistirin.)
if exist "%VENV%" rmdir /s /q "%VENV%"
pause
exit /b 1

:zipten
echo.
echo Bu dosya zip'in icinden calistirildi. Once zip'i klasore cikarmaniz gerekiyor:
echo   1. Bu pencereyi kapatin.
echo   2. Indirdiginiz zip dosyasina sag tiklayip "Tumunu ayikla" deyin
echo      (ornegin Belgeler klasorune).
echo   3. Cikan klasordeki maliyet-analizi\baslat.bat dosyasini calistirin.
echo.
pause
exit /b 1
