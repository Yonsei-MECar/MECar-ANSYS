[CmdletBinding()]
param(
    [switch]$AllowDownload,
    [string]$PythonCommand = "python",
    [string]$ToolsRoot = "C:\MECarTools\fluent-2d-runner",
    [string]$WheelCache = "C:\MECarRuntime\downloads\gmsh-4.13.1"
)

$ErrorActionPreference = "Stop"
$expectedName = "gmsh-4.13.1-py2.py3-none-win_amd64.whl"
$expectedHash = "00F3C86B3146C1AF1259E695ED646880C9DA0C2DED2D1E48B240A1D3D194BAE6"
$wheel = Join-Path $WheelCache $expectedName

if (-not (Test-Path -LiteralPath $wheel)) {
    if (-not $AllowDownload) {
        throw "Pinned Gmsh wheel is absent. Re-run with -AllowDownload to fetch it from PyPI, then verify SHA-256 before installation."
    }
    New-Item -ItemType Directory -Path $WheelCache -Force | Out-Null
    & $PythonCommand -m pip download --no-deps --only-binary=:all: gmsh==4.13.1 --dest $WheelCache
    if ($LASTEXITCODE -ne 0) { throw "Gmsh wheel download failed." }
}

$actualHash = (Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash
if ($actualHash -ne $expectedHash) {
    throw "Pinned Gmsh wheel checksum mismatch. Expected $expectedHash but found $actualHash."
}

$venv = Join-Path $ToolsRoot ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    New-Item -ItemType Directory -Path $ToolsRoot -Force | Out-Null
    & $PythonCommand -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the isolated Python environment." }
}

& $venvPython -m pip install --no-deps $wheel
if ($LASTEXITCODE -ne 0) { throw "Pinned Gmsh installation failed." }
& $venvPython -c "import gmsh; assert gmsh.__version__ == '4.13.1'; print('gmsh', gmsh.__version__)"
if ($LASTEXITCODE -ne 0) { throw "Gmsh import/version verification failed." }

Write-Output "Verified Gmsh environment: $venvPython"

