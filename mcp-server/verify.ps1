#requires -version 5.1
[CmdletBinding()]
param(
    [string]$VenvPath = (Join-Path $env:LOCALAPPDATA 'MECar\ansys-mcp-server\venv-py311'),
    [string]$RunLocation = 'C:\MECarRuntime\ansys',
    [switch]$LaunchMapdl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()

$python = Join-Path ([IO.Path]::GetFullPath($VenvPath)) 'Scripts\python.exe'
$runLocationResolved = [IO.Path]::GetFullPath($RunLocation)
$lockFile = Join-Path $PSScriptRoot 'requirements.lock.txt'
$lockVerifier = Join-Path $PSScriptRoot 'verify_dependency_lock.py'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Virtual environment is missing. Run install.ps1 first.'
}
if ($runLocationResolved -match '[^\x00-\x7F]' -or $runLocationResolved.Contains(' ')) {
    throw 'RunLocation must use an ASCII path without spaces for MAPDL 2021 R1 compatibility.'
}
New-Item -ItemType Directory -Path $runLocationResolved -Force | Out-Null
$env:ANSYS_MCP_RUN_LOCATION = $runLocationResolved

& $python $lockVerifier $lockFile
if ($LASTEXITCODE -ne 0) { throw 'Installed dependency versions do not match the validated lock. Rerun install.ps1.' }
& $python -m pip check --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw 'Installed dependency metadata is inconsistent.' }

Push-Location $PSScriptRoot
try {
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed.' }
} finally {
    Pop-Location
}
& $python -c "from ansys_mcp_server.server import backend; import json; print(json.dumps(backend.status(), indent=2))"
if ($LASTEXITCODE -ne 0) { throw 'Server import/status check failed.' }
& $python -m ansys_mcp_server.smoke
if ($LASTEXITCODE -ne 0) { throw 'MCP STDIO handshake failed.' }

if ($LaunchMapdl) {
    Write-Host 'Launching MAPDL for a live gRPC solve/result/exit smoke test...'
    & $python -m ansys_mcp_server.live_smoke
    if ($LASTEXITCODE -ne 0) { throw 'Live MAPDL test failed.' }
}

Write-Host 'Verification completed.' -ForegroundColor Green
