# Convenience script for local development on Windows.
# Usage: from the project root, run:  .\scripts\dev.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example (DEMO_MODE=true by default)."
}

& ".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
