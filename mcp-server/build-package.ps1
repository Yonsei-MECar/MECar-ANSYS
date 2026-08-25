#requires -version 5.1
[CmdletBinding()]
param([string]$Version = '0.1.1')

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()

$serverRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$dist = Join-Path $serverRoot 'dist'
$stage = Join-Path $dist "mecar-ansys-mcp-server-$Version"
$zip = Join-Path $dist "mecar-ansys-mcp-server-$Version.zip"
$checksum = "$zip.sha256"

New-Item -ItemType Directory -Path $dist -Force | Out-Null
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
if (Test-Path -LiteralPath $checksum) { Remove-Item -LiteralPath $checksum -Force }
New-Item -ItemType Directory -Path $stage | Out-Null

$items = @('src', 'tests', 'pyproject.toml', 'requirements.lock.txt', 'verify_dependency_lock.py', 'README_KO.md', 'SOURCES.md', 'LICENSE', '.gitignore', 'config.example.toml', 'install.ps1', 'verify.ps1', 'build-package.ps1')
foreach ($item in $items) {
    $source = Join-Path $serverRoot $item
    if (Test-Path -LiteralPath $source -PathType Container) {
        Get-ChildItem -LiteralPath $source -Recurse -File |
            Where-Object { $_.FullName -notmatch '\\(__pycache__|\.pytest_cache)\\' -and $_.Extension -notin @('.pyc', '.pyo') } |
            ForEach-Object {
                $relative = $_.FullName.Substring($serverRoot.Length).TrimStart('\')
                $destination = Join-Path $stage $relative
                New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $destination
            }
    } else {
        Copy-Item -LiteralPath $source -Destination $stage
    }
}
Compress-Archive -LiteralPath $stage -DestinationPath $zip -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($checksum, "$hash  $([IO.Path]::GetFileName($zip))`r`n", [Text.UTF8Encoding]::new($false))
Write-Host "Created $zip"
Write-Host "SHA256 $hash" -ForegroundColor Green
