$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
# Verify the saved identity before stopping anything: PIDs can be reused by Windows.
foreach ($entry in @(@('mobile-tunnel.pid','cloudflared'),@('mobile-backend.pid','serve_demo.py'))) {
    $pidPath = Join-Path $PSScriptRoot ('.cache/' + $entry[0])
    if (-not (Test-Path -LiteralPath $pidPath)) { continue }
    $savedPid = [int](Get-Content -LiteralPath $pidPath)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$savedPid"
    if ($process -and $process.CommandLine.Contains($entry[1]) -and
        ($process.ExecutablePath.StartsWith($PSScriptRoot) -or $process.CommandLine.Contains($PSScriptRoot))) {
        # Python on Windows may launch a child interpreter. Stop only verified children.
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$savedPid" | ForEach-Object {
            if ($_.CommandLine.Contains('serve_demo.py') -and $_.CommandLine.Contains('8766')) {
                Stop-Process -Id $_.ProcessId
            }
        }
        Stop-Process -Id $savedPid -ErrorAction SilentlyContinue
    }
}
Write-Host 'Ponte móvel encerrada. O site continua publicado, sem processar novas fotos.'
