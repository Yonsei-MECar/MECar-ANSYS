[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Python = "C:\MECarTools\fluent-2d-runner\.venv\Scripts\python.exe",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RunnerArgs
)

$packageRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Verified runner Python not found at $Python. Run setup_gmsh.ps1 first."
}
$env:PYTHONPATH = Join-Path $packageRoot "src"
& $Python -m mecar_fluent2d @RunnerArgs
exit $LASTEXITCODE

