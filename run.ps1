# Ontario Parks Roofed Watcher - Windows helper
# Usage:
#   .\run.ps1
#   .\run.ps1 -Reserve
#   .\run.ps1 -Config config.json -- --list-parks

param(
  [string]$Config = "config.json",
  [switch]$Reserve
)

$ErrorActionPreference = "Stop"

function Write-Info($msg) {
  Write-Host $msg
}

function Write-Warn($msg) {
  Write-Host $msg -ForegroundColor Yellow
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Warn "Python not found. Install Python 3.10+ from https://www.python.org/downloads/ and check 'Add Python to PATH'."
  exit 1
}

if (-not (Test-Path ".venv\\Scripts\\python.exe")) {
  Write-Info "Creating virtual environment..."
  python -m venv .venv
}

$venvPy = ".venv\\Scripts\\python.exe"

Write-Info "Installing dependencies..."
& $venvPy -m pip install -r requirements.txt

if (-not (Test-Path "tmp")) {
  New-Item -ItemType Directory -Path "tmp" | Out-Null
}

if (-not (Test-Path $Config)) {
  Copy-Item "config.example.json" $Config
  Write-Warn "Created $Config. Edit it to set parks/dates, then run again."
  exit 0
}

if (-not (Test-Path "tmp\\op_cookies.json")) {
  Write-Warn "Cookie file not found: tmp\\op_cookies.json"
  Write-Warn "Export your browser cookies to that file before running."
}

$scriptArgs = @("scripts\\op_roofed_watch.py", "--use-config", "--config", $Config)
if ($Reserve) {
  $scriptArgs += "--reserve"
}

if ($Args.Count -gt 0) {
  $scriptArgs += $Args
}

Write-Info "Running watcher..."
& $venvPy @scriptArgs
