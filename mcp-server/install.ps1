#requires -version 5.1
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$AnsysRoot = 'C:\Program Files\ANSYS Inc\v211',
    [string]$VenvPath = (Join-Path $env:LOCALAPPDATA 'MECar\ansys-mcp-server\venv-py311'),
    [string]$RunLocation = 'C:\MECarRuntime\ansys',
    [string]$Wheelhouse,
    [switch]$Offline,
    [switch]$EnableRawApdl,
    [switch]$EnableWorkbenchScripts,
    [switch]$DisableRawApdl,
    [switch]$DisableWorkbenchScripts,
    [switch]$SkipCodexConfig
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()

$serverRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$projectPath = [IO.Path]::GetFullPath($ProjectRoot)
$venvPathResolved = [IO.Path]::GetFullPath($VenvPath)
$runLocationResolved = [IO.Path]::GetFullPath($RunLocation)
$venvPython = Join-Path $venvPathResolved 'Scripts\python.exe'
$lockFile = Join-Path $serverRoot 'requirements.lock.txt'
$lockVerifier = Join-Path $serverRoot 'verify_dependency_lock.py'

function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($selector in @('-3.11', '-3.12', '-3.10')) {
            & $py.Source $selector -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return @($py.Source, $selector) }
        }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return @($python.Source) }
    }
    throw 'Python 3.10-3.12 is required. Install Python, then rerun install.ps1.'
}

function ConvertTo-TomlLiteral([string]$Value) {
    return "'" + $Value.Replace("'", "''") + "'"
}

function Remove-McpTable([string]$Content, [string]$ServerName) {
    $target = "^\s*\[mcp_servers\.$([Regex]::Escape($ServerName))(?:\.[^\]]+)?\]\s*$"
    $anyTable = '^\s*\[[^\]]+\]\s*$'
    $result = New-Object 'System.Collections.Generic.List[string]'
    $skipping = $false
    foreach ($line in ($Content -split "`r?`n")) {
        if ($line -match $target) { $skipping = $true; continue }
        if ($skipping -and $line -match $anyTable) { $skipping = $false }
        if (-not $skipping) { $result.Add($line) }
    }
    return ($result -join "`r`n").Trim()
}

if (-not (Test-Path -LiteralPath $projectPath -PathType Container)) {
    throw "ProjectRoot does not exist: $projectPath"
}
if (-not (Test-Path -LiteralPath $lockFile -PathType Leaf)) {
    throw "Dependency lock is missing: $lockFile"
}
if (-not (Test-Path -LiteralPath $lockVerifier -PathType Leaf)) {
    throw "Dependency lock verifier is missing: $lockVerifier"
}
if ($Offline -and [string]::IsNullOrWhiteSpace($Wheelhouse)) {
    throw '-Offline requires -Wheelhouse with all locked distributions.'
}
if ($runLocationResolved -match '[^\x00-\x7F]' -or $runLocationResolved.Contains(' ')) {
    throw 'RunLocation must use an ASCII path without spaces for MAPDL 2021 R1 compatibility.'
}
New-Item -ItemType Directory -Path $runLocationResolved -Force | Out-Null

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    $launcher = Find-Python
    $venvParent = Split-Path -Parent $venvPathResolved
    New-Item -ItemType Directory -Path $venvParent -Force | Out-Null
    Write-Host "Creating virtual environment: $venvPathResolved"
    if ($launcher.Count -eq 2) {
        & $launcher[0] $launcher[1] -m venv $venvPathResolved
    } else {
        & $launcher[0] -m venv $venvPathResolved
    }
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment (exit $LASTEXITCODE)." }
}

Write-Host 'Installing the exact hashed dependency lock...'
$dependencyInstallArgs = @(
    '-m', 'pip', 'install',
    '--disable-pip-version-check',
    '--require-hashes',
    '--only-binary=:all:',
    '-r', $lockFile
)
if (-not [string]::IsNullOrWhiteSpace($Wheelhouse)) {
    $wheelhouseResolved = [IO.Path]::GetFullPath($Wheelhouse)
    if (-not (Test-Path -LiteralPath $wheelhouseResolved -PathType Container)) {
        throw "Wheelhouse does not exist: $wheelhouseResolved"
    }
    if ($Offline) { $dependencyInstallArgs += '--no-index' }
    $dependencyInstallArgs += @('--find-links', $wheelhouseResolved)
}
& $venvPython @dependencyInstallArgs
if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed.' }

Write-Host 'Installing the local Ansys MCP package without dependency resolution...'
& $venvPython -m pip install --disable-pip-version-check --no-deps --no-build-isolation $serverRoot
if ($LASTEXITCODE -ne 0) { throw 'Local package installation failed.' }
& $venvPython $lockVerifier $lockFile
if ($LASTEXITCODE -ne 0) { throw 'Installed dependency versions do not match the validated lock.' }
& $venvPython -m pip check --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw 'Installed dependency metadata is inconsistent.' }

if (-not $SkipCodexConfig) {
    $configDirectory = Join-Path $projectPath '.codex'
    $configPath = Join-Path $configDirectory 'config.toml'
    New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null
    $existing = if (Test-Path -LiteralPath $configPath) { [IO.File]::ReadAllText($configPath) } else { '' }
    if ($existing) {
        $backup = "$configPath.bak.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Copy-Item -LiteralPath $configPath -Destination $backup
        Write-Host "Backed up existing Codex config: $backup"
    }
    $existing = Remove-McpTable $existing 'ansys_2021r1'
    if ($EnableRawApdl -and $DisableRawApdl) { throw 'Choose only one of EnableRawApdl or DisableRawApdl.' }
    if ($EnableWorkbenchScripts -and $DisableWorkbenchScripts) { throw 'Choose only one of EnableWorkbenchScripts or DisableWorkbenchScripts.' }
    $allowRawApdl = if ($EnableRawApdl -and -not $DisableRawApdl) { '1' } else { '0' }
    $allowWorkbenchScripts = if ($EnableWorkbenchScripts -and -not $DisableWorkbenchScripts) { '1' } else { '0' }
    $block = @"
[mcp_servers.ansys_2021r1]
command = $(ConvertTo-TomlLiteral $venvPython)
args = ['-m', 'ansys_mcp_server.server']
env = { ANSYS_MCP_VERSION = '211', ANSYS_MCP_ANSYS_ROOT = $(ConvertTo-TomlLiteral ([IO.Path]::GetFullPath($AnsysRoot))), ANSYS_MCP_MAPDL_EXE = $(ConvertTo-TomlLiteral (Join-Path ([IO.Path]::GetFullPath($AnsysRoot)) 'ansys\bin\winx64\ANSYS211.exe')), ANSYS_MCP_WORK_ROOT = $(ConvertTo-TomlLiteral $projectPath), ANSYS_MCP_RUN_LOCATION = $(ConvertTo-TomlLiteral $runLocationResolved), ANSYS_MCP_ALLOW_RAW_APDL = '$allowRawApdl', ANSYS_MCP_ALLOW_WB_SCRIPTS = '$allowWorkbenchScripts' }
enabled = true
required = false
startup_timeout_sec = 120
tool_timeout_sec = 1800
default_tools_approval_mode = 'writes'
"@
    $newConfig = if ($existing) { $existing + "`r`n`r`n" + $block.Trim() + "`r`n" } else { $block.Trim() + "`r`n" }
    [IO.File]::WriteAllText($configPath, $newConfig, [Text.UTF8Encoding]::new($false))
    Write-Host "Configured Codex MCP server in $configPath"
    if ($allowRawApdl -eq '1' -or $allowWorkbenchScripts -eq '1') {
        Write-Warning 'Raw APDL and/or Workbench scripts are enabled. They can execute commands and access files outside ANSYS_MCP_WORK_ROOT.'
    }
}

Push-Location $serverRoot
try {
    & $venvPython -m pytest
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
} finally {
    Pop-Location
}
Write-Host 'Installation complete. Restart Codex for the new MCP server to appear.' -ForegroundColor Green
