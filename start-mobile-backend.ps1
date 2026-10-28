$ErrorActionPreference = 'Stop'
$Port = 8766
Set-Location -LiteralPath $PSScriptRoot
$settingsPath = Join-Path $PSScriptRoot '.cache/mobile-bridge.json'
$pythonPath = Join-Path $PSScriptRoot 'experiments/.venv/Scripts/python.exe'
$tunnelPath = Join-Path $PSScriptRoot '.cache/cloudflared.exe'
foreach ($required in @($settingsPath,$pythonPath,$tunnelPath)) {
    if (-not (Test-Path -LiteralPath $required)) { throw 'Instalação móvel incompleta. Peça para reconfigurar a demonstração.' }
}
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $owner = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess)
    if (-not $owner.CommandLine.Contains('serve_demo.py') -or -not $owner.CommandLine.Contains('--bridge-config')) {
        throw 'A porta da demonstração está ocupada por outro programa. A ponte não foi aberta.'
    }
} else {
    $backend = Start-Process -FilePath $pythonPath -WorkingDirectory $PSScriptRoot -WindowStyle Hidden `
        -ArgumentList @('-X','utf8','experiments/serve_demo.py','--port',"$Port",'--bridge-config','.cache/mobile-bridge.json') `
        -RedirectStandardOutput '.cache/mobile-backend.out.log' -RedirectStandardError '.cache/mobile-backend.err.log' -PassThru
    $backend.Id | Set-Content '.cache/mobile-backend.pid'
}
$tunnel = $null
$pidPath = Join-Path $PSScriptRoot '.cache/mobile-tunnel.pid'
if (Test-Path -LiteralPath $pidPath) {
    $savedPid = [int](Get-Content -LiteralPath $pidPath)
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$savedPid"
    if ($candidate -and $candidate.ExecutablePath -eq $tunnelPath) { $tunnel = $candidate }
}
if (-not $tunnel) {
    $tunnel = Start-Process -FilePath $tunnelPath -WorkingDirectory $PSScriptRoot -WindowStyle Hidden `
        -ArgumentList @('tunnel','--url',"http://127.0.0.1:$Port",'--no-autoupdate') `
        -RedirectStandardOutput '.cache/mobile-tunnel.out.log' -RedirectStandardError '.cache/mobile-tunnel.err.log' -PassThru
    $tunnel.Id | Set-Content $pidPath
}
$bridgeUrl = $null
for ($attempt=0; $attempt -lt 30; $attempt++) {
    $log = Get-Content '.cache/mobile-tunnel.err.log' -Raw -ErrorAction SilentlyContinue
    if ($log -match 'https://[a-z0-9-]+\.trycloudflare\.com') { $bridgeUrl=$Matches[0]; break }
    Start-Sleep -Seconds 1
}
if (-not $bridgeUrl) { throw 'A ponte ainda não conectou. Confira a Internet e tente novamente.' }
$settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
if ($settings.BACKEND_URL -ne $bridgeUrl) {
    $settings.BACKEND_URL = $bridgeUrl
    $settings | ConvertTo-Json | Set-Content -LiteralPath $settingsPath -Encoding utf8
    Write-Host 'A ponte foi reiniciada e mudou de endereço. Peça ao assistente para reativar o link da demonstração.' -ForegroundColor Yellow
} else {
    Write-Host 'Ponte da demonstração ativa. Mantenha este PC ligado, acordado e conectado à Internet.' -ForegroundColor Green
}
Write-Host 'Site: https://bixdata-caixa-demo.vercel.app'
