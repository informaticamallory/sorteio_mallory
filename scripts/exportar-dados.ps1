# Empacota banco, chave de identificacao, chaves do push e imagens em um .zip
# para levar ao servidor novo (Easypanel). Ver docs\publicar-easypanel.md.
#   powershell -ExecutionPolicy Bypass -File .\scripts\exportar-dados.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\exportar-dados.ps1 -Destino C:\temp
#
# Pare o servidor do evento antes: o que for feito depois da exportacao nao
# vai junto. O .zip tem dados pessoais - nao deixe no OneDrive nem mande por e-mail.

param([string]$Destino = '')

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$python = Join-Path $raiz 'backend\.venv\Scripts\python.exe'

Set-Location (Join-Path $raiz 'backend')
if ($Destino) { & $python -m app.exportar_dados $Destino } else { & $python -m app.exportar_dados }
if ($LASTEXITCODE -ne 0) { throw "Falha ao exportar os dados." }
