$ErrorActionPreference = 'Stop'
$RuntimePath = Join-Path $env:LOCALAPPDATA 'AI-Previz-Director\runtime.json'
if (-not (Test-Path -LiteralPath $RuntimePath)) { throw 'Runtime configuration is missing.' }
$Runtime = Get-Content -Raw -LiteralPath $RuntimePath | ConvertFrom-Json
$Headers = @{ 'X-AI-Previz-Token' = $Runtime.token }
$Health = Invoke-RestMethod -Uri "http://127.0.0.1:$($Runtime.port)/health" -TimeoutSec 3
$Status = Invoke-RestMethod -Uri "http://127.0.0.1:$($Runtime.port)/status" -Headers $Headers -TimeoutSec 3
[pscustomobject]@{ Bridge=$Health.ok; BlenderConnected=$Status.blender_connected; Queue=$Status.queued; Port=$Runtime.port }

