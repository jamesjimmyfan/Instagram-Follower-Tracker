#!/bin/bash
set -e
cd "$(dirname "$0")"
python3 -m pip install --upgrade pyinstaller
python3 -m PyInstaller --noconfirm --clean --windowed --name InstagramFollowerTracker app.py
echo 'Built: dist/InstagramFollowerTracker.app'
