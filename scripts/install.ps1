$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BlenderExe = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
if (-not (Test-Path -LiteralPath $BlenderExe)) { throw "Blender 5.2 not found: $BlenderExe" }
$AddonRoot = Join-Path $env:APPDATA 'Blender Foundation\Blender\5.2\scripts\addons'
$Destination = Join-Path $AddonRoot 'ai_previz_director'
New-Item -ItemType Directory -Force -Path $AddonRoot | Out-Null
if (Test-Path -LiteralPath $Destination) {
    $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Move-Item -LiteralPath $Destination -Destination "$Destination.backup-$Stamp"
}
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'addon\ai_previz_director') -Destination $Destination -Recurse

Push-Location $ProjectRoot
try { uv sync --python 3.12 } finally { Pop-Location }

$RuntimeDir = Join-Path $env:LOCALAPPDATA 'AI-Previz-Director'
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
$RuntimePath = Join-Path $RuntimeDir 'runtime.json'
if (Test-Path -LiteralPath $RuntimePath) {
    $Runtime = Get-Content -Raw -LiteralPath $RuntimePath | ConvertFrom-Json
    $Token = $Runtime.token
} else {
    $Bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($Bytes)
    $Token = [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}
@{ host='127.0.0.1'; port=8765; token=$Token } | ConvertTo-Json | Set-Content -LiteralPath $RuntimePath -Encoding utf8

& $BlenderExe --background --python-expr "import bpy; bpy.ops.preferences.addon_enable(module='ai_previz_director'); bpy.ops.wm.save_userpref(); print('AI_PREVIZ_ADDON_ENABLED', 'ai_previz_director' in bpy.context.preferences.addons)"

$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$McpScript = Join-Path $ProjectRoot 'companion_mcp\server.py'
$Existing = codex mcp list | Out-String
if ($Existing -match '(?m)^ai-previz-director\s') { codex mcp remove ai-previz-director | Out-Null }
codex mcp add ai-previz-director -- $PythonExe $McpScript | Out-Null

Write-Host "Installed AI Previz Director to $Destination"
Write-Host "Runtime config: $RuntimePath"
Write-Host "Companion MCP: ai-previz-director"

