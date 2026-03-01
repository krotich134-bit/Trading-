param(
  [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot\..

if ($Clean) {
  if (Test-Path dist) { Remove-Item dist -Recurse -Force }
  if (Test-Path build) { Remove-Item build -Recurse -Force }
  Get-ChildItem -Recurse -Include *.egg-info | Remove-Item -Recurse -Force
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "Python not found on PATH. Install Python 3.11+ and retry." -ForegroundColor Yellow
  Pop-Location
  exit 1
}

python -m pip install --upgrade pip
python -m pip install build wheel
python -m build

Write-Host "Build complete. Artifacts in dist/:" -ForegroundColor Green
Get-ChildItem dist

Pop-Location

