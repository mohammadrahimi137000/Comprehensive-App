# Build the Windows desktop application into dist/ComprehensiveApp.
$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
}

$Python = ".\.venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install "pyinstaller>=6.10,<7"

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name ComprehensiveApp `
    --collect-all PySide6 `
    --collect-all cv2 `
    --collect-all signalrcore `
    --collect-all pytesseract `
    --hidden-import win32gui `
    --hidden-import win32process `
    --hidden-import pywintypes `
    --hidden-import pythoncom `
    main.py

Write-Host ""
Write-Host "Build complete: dist\ComprehensiveApp\ComprehensiveApp.exe"