param(
    [ValidateRange(1024, 65535)][int]$Port = 8765,
    [ValidateSet('cuda', 'cpu')][string]$Device = 'cuda'
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$uvPath = if ($uvCommand) { $uvCommand.Source } else {
    Join-Path $env:USERPROFILE '.local/bin/uv.exe'
}
if (-not (Test-Path -LiteralPath $uvPath)) {
    throw 'uv não encontrado. Instale pelo site oficial e execute novamente.'
}
Write-Host "Demonstração assistida: http://127.0.0.1:$Port — preços fictícios."
& $uvPath run --locked --project experiments python experiments/serve_demo.py --port $Port --device $Device
exit $LASTEXITCODE
