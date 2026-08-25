[CmdletBinding()]
param(
    [string]$Python = "C:\MECarTools\fluent-2d-runner\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$packageRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Verified runner Python not found at $Python. Run setup_gmsh.ps1 first."
}
$env:PYTHONPATH = Join-Path $packageRoot "src"
& $Python -m unittest discover -s (Join-Path $packageRoot "tests") -v
if ($LASTEXITCODE -ne 0) { throw "Fluent 2D runner tests failed." }

