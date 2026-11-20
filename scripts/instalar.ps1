# Instalacao completa do projeto. Execute uma vez.
#   powershell -ExecutionPolicy Bypass -File .\scripts\instalar.ps1

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot

Write-Host "== Backend ==" -ForegroundColor Cyan
Set-Location (Join-Path $raiz 'backend')
if (-not (Test-Path '.venv')) { py -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host "Criado backend\.env a partir do exemplo. TROQUE SECRET_KEY e ADMIN_SENHA." -ForegroundColor Yellow
}

Write-Host "== Frontend ==" -ForegroundColor Cyan
Set-Location (Join-Path $raiz 'frontend')
npm install --no-audit --no-fund

Set-Location $raiz
Write-Host ""
Write-Host "Instalacao concluida." -ForegroundColor Green
Write-Host "  Dados de demonstracao : .\scripts\carregar-demo.ps1"
Write-Host "  Desenvolvimento       : .\scripts\iniciar-dev.ps1"
Write-Host "  Evento (producao)     : .\scripts\iniciar-evento.ps1"
