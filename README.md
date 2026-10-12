# Instagram Follower Tracker — macOS & Windows

A local desktop application using Python's built-in Tkinter GUI and SQLite. No Instagram password, scraping, or API key needed. The app uses official Instagram JSON export ZIP archives only.

## Start immediately (Python installed)

- Extract this project, then open a terminal in this folder.
- **macOS:** `python3 app.py`
- **Windows / Lenovo Yoga:** `py app.py` (or `python app.py`)
- Python's Tkinter module must be installed (normally included with Python from python.org; on macOS, use a Python distribution with Tk support).

Click **Import Instagram ZIP…** and choose the ZIP downloaded from Accounts Center → Export your information → Followers and following → All time → JSON.

Alternatively click **Open Inbox**, place the ZIP there, and leave the app running. It checks for new ZIP files every 30 seconds. No need to unzip exports. It may take some time for Instagram to prepare an export.

The app shows non-followers, non-mutual followers, newly gained and missing followers, plus creates CSV reports for every new import.

## Build the desktop applications

Python executables must be built **on their target operating system**, not cross-compiled:

- **On macOS:** run `./build_mac.sh` inside this directory. Result: `dist/InstagramFollowerTracker.app`.
- **On Windows:** double-click `build_windows.bat` (requires Python installed). Result: `dist\InstagramFollowerTracker.exe`.

The scripts install PyInstaller through pip. The result includes a Python runtime so **end users do not need Python installed**. On macOS, an unsigned app can trigger Gatekeeper; on Windows, an unsigned exe may trigger SmartScreen. For public distribution, sign/notarize appropriately. Build on an Apple Silicon Mac for arm64 Macs, or Intel Mac for x86_64; Windows builds should match the target Windows architecture (typical Lenovo Yoga x64).

## Storage location

Data is **not stored inside the .app or .exe**, so updating the program preserves your history.

- macOS: `~/Library/Application Support/InstagramFollowerTracker/`
- Windows: `%LOCALAPPDATA%\InstagramFollowerTracker\`

Within the folder: `inbox/`, `reports/`, and `tracker.sqlite3`.

### Migrating your existing command-line tracker history

Close the desktop app. Copy `tracker.sqlite3` and `reports/` from the original `instagram_tracker` folder into the new application storage location above, then reopen the app. Alternatively, just import your original Instagram ZIP archives again in chronological order.

## Important limits

- Data updates when you manually download a new official Instagram export; the app cannot initiate Instagram's export.
- Export snapshots show username changes, deletions, and unfollows alike, so 'lost followers' are not definitive unfollows.
- Use **one Instagram account per database**. Do not mix exports from multiple accounts.
- The app performs all comparisons locally; do not upload your export to unknown third-party services.
