# Runs the evaluation harness (see evaluation/run_evaluation.py) and prints
# the measured verification/conflict-detection/calibration metrics.
# Usage: from the project root, run:  .\scripts\run_evaluation.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
& ".venv\Scripts\python.exe" -m evaluation.run_evaluation
