$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PythonExe)) { throw 'Run install.ps1 first.' }
$Existing = Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue
if ($Existing) { Write-Host 'AI Previz Bridge is already listening on 127.0.0.1:8765'; exit 0 }
$Process = Start-Process -FilePath $PythonExe -ArgumentList '-m','bridge.server','--port','8765' -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
$PidPath = Join-Path $env:LOCALAPPDATA 'AI-Previz-Director\bridge.pid'
$Process.Id | Set-Content -LiteralPath $PidPath -Encoding ascii
Start-Sleep -Milliseconds 800
Write-Host "AI Previz Bridge started. PID=$($Process.Id)"

