# Cria (ou recria) o evento de demonstracao com dados ficticios.
# Use -Limpar para apenas remover os eventos de demonstracao.
#   powershell -ExecutionPolicy Bypass -File .\scripts\carregar-demo.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\carregar-demo.ps1 -Limpar

param([switch]$Limpar)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $raiz 'backend')

if ($Limpar) { .\.venv\Scripts\python.exe -m app.seed --limpar }
else { .\.venv\Scripts\python.exe -m app.seed }
