# One-time setup of the Homeschooling home server on the family's Windows computer.
# Run from the repository folder (outside Google Drive and OneDrive), e.g.
#   git clone https://github.com/hermann-ago/Homeschooling "$env:USERPROFILE\source\Homeschooling"
#   cd "$env:USERPROFILE\source\Homeschooling"; powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if ($root -match "Google Drive|My Drive|OneDrive|^G:") { throw "Clone the repository outside Google Drive and OneDrive." }
Set-Location $root
if (-not (Test-Path "backend\venv")) { py -3 -m venv backend\venv }
& backend\venv\Scripts\python.exe -m pip install --upgrade pip
& backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Push-Location frontend
npm ci --legacy-peer-deps
npm run build
Pop-Location
Write-Host "Setup complete. Start the server with 'Start Homeschooling.cmd'."
