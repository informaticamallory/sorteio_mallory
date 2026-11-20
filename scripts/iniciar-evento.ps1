# Modo evento: build do frontend e um unico servidor na porta 8000,
# acessivel pela rede local (painel no celular, telao no projetor).
#   powershell -ExecutionPolicy Bypass -File .\scripts\iniciar-evento.ps1
#
# Por padrao o servidor sobe em HTTPS com um certificado da rede local
# (necessario para o scanner de QR Code pela camera do celular). Cada aparelho
# mostra uma vez o aviso "conexao nao e particular": toque em Avancado >
# Continuar. Para voltar ao HTTP simples:
#   powershell -ExecutionPolicy Bypass -File .\scripts\iniciar-evento.ps1 -SemHttps

param([int]$Porta = 8000, [switch]$SemHttps)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$python = Join-Path $raiz 'backend\.venv\Scripts\python.exe'

Write-Host "Gerando build do frontend..." -ForegroundColor Cyan
Set-Location (Join-Path $raiz 'frontend')
npm run build
if ($LASTEXITCODE -ne 0) { throw "Falha no build do frontend." }

$ips = @(Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -ExpandProperty IPAddress)

Set-Location (Join-Path $raiz 'backend')
$argsSsl = @()
$esquema = 'http'
if (-not $SemHttps) {
    $saida = & $python -m app.certificado_local @ips
    if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar o certificado HTTPS." }
    $cert = ($saida | Where-Object { $_ -like 'CERT=*' }) -replace '^CERT=', ''
    $chave = ($saida | Where-Object { $_ -like 'CHAVE=*' }) -replace '^CHAVE=', ''
    $ca = ($saida | Where-Object { $_ -like 'CA=*' }) -replace '^CA=', ''
    $argsSsl = @('--ssl-certfile', $cert, '--ssl-keyfile', $chave)
    $esquema = 'https'
}

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Green
Write-Host " Enderecos para o evento (porta $Porta, $($esquema.ToUpper()))" -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Green
Write-Host "  Nesta maquina : ${esquema}://localhost:$Porta"
foreach ($ip in $ips) { Write-Host "  Na rede local : ${esquema}://${ip}:$Porta" }
Write-Host ""
if (-not $SemHttps) {
    Write-Host " HTTPS com certificado da rede local: na primeira vez, cada aparelho" -ForegroundColor Yellow
    Write-Host " avisa 'conexao nao e particular'. Toque em Avancado > Continuar." -ForegroundColor Yellow
    Write-Host " Para tirar o aviso de vez, instale no aparelho a autoridade:" -ForegroundColor Yellow
    Write-Host "   $ca (ou ca.cer na mesma pasta)"
    Write-Host ""
}
Write-Host " O link do telao esta em Configuracao > Link do telao." -ForegroundColor Yellow
Write-Host " Se outro dispositivo nao conectar, libere a porta no firewall:" -ForegroundColor Yellow
Write-Host "   New-NetFirewallRule -DisplayName 'Sorteio' -Direction Inbound -LocalPort $Porta -Protocol TCP -Action Allow"
Write-Host ""

& $python -m uvicorn app.main:app --host 0.0.0.0 --port $Porta @argsSsl
