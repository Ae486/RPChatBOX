$ErrorActionPreference = "Stop"

Write-Host "Building ChatBox Backend for Desktop (Windows)..."

Push-Location "$PSScriptRoot\.."

# Install PyInstaller if needed
pip show pyinstaller 2>$null
if ($LASTEXITCODE -ne 0) {
    pip install pyinstaller
}

# Build using spec file
if (Test-Path "build\chatbox-backend.spec") {
    pyinstaller --distpath dist --workpath build\pyinstaller --clean build\chatbox-backend.spec
} else {
    pyinstaller --onefile --name chatbox-backend --distpath dist --workpath build\pyinstaller main.py
}

if (Test-Path "dist\chatbox-backend.exe") {
    $size = (Get-Item "dist\chatbox-backend.exe").Length / 1MB
    Write-Host "Build complete: dist\chatbox-backend.exe ($([math]::Round($size, 1)) MB)"
} else {
    Write-Host "Build FAILED" -ForegroundColor Red
    exit 1
}

Pop-Location
