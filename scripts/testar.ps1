# Roda a suite de testes do backend.
#   powershell -ExecutionPolicy Bypass -File .\scripts\testar.ps1

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $raiz 'backend')
.\.venv\Scripts\python.exe -m pytest -v
