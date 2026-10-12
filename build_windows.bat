@echo off
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --onefile --name InstagramFollowerTracker app.py
if errorlevel 1 exit /b 1
echo Built: dist\InstagramFollowerTracker.exe
pause
