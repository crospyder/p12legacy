@echo off
setlocal

cd /d %~dp0

if not exist .venv (
  py -3 -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

pyinstaller --noconfirm --onedir --windowed --name P12LegacyConverter src\p12legacy_converter.py

echo.
echo Build gotov: dist\P12LegacyConverter\P12LegacyConverter.exe
echo Uz EXE dodaj portable OpenSSL folder: dist\P12LegacyConverter\openssl\
pause
