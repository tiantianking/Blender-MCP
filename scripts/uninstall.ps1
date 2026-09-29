$ErrorActionPreference = 'Stop'
$BlenderExe = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
$AddonPath = Join-Path $env:APPDATA 'Blender Foundation\Blender\5.2\scripts\addons\ai_previz_director'
if (Test-Path -LiteralPath $BlenderExe) {
    & $BlenderExe --background --python-expr "import bpy; bpy.ops.preferences.addon_disable(module='ai_previz_director'); bpy.ops.wm.save_userpref()"
}
if (Test-Path -LiteralPath $AddonPath) {
    $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Move-Item -LiteralPath $AddonPath -Destination "$AddonPath.removed-$Stamp"
    Write-Host "Addon moved to recoverable backup: $AddonPath.removed-$Stamp"
}
$Existing = codex mcp list | Out-String
if ($Existing -match '(?m)^ai-previz-director\s') { codex mcp remove ai-previz-director | Out-Null }
$PidPath = Join-Path $env:LOCALAPPDATA 'AI-Previz-Director\bridge.pid'
if (Test-Path -LiteralPath $PidPath) {
    $BridgePid = [int](Get-Content -LiteralPath $PidPath)
    $Process = Get-CimInstance Win32_Process -Filter "ProcessId=$BridgePid" -ErrorAction SilentlyContinue
    if ($Process -and $Process.CommandLine -like '*bridge.server*') { Stop-Process -Id $BridgePid -Force }
}

