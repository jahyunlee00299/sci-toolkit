#Requires -Version 5.1
<#
.SYNOPSIS
    doctor.ps1 - Windows one-command wrapper for doctor.py.

.DESCRIPTION
    Locates a usable Python interpreter (py launcher, then python, then
    python3), then invokes doctor.py from the SAME directory as this script
    (script-relative, no hardcoded paths) so it works no matter where the
    sci-toolkit folder is copied to (USB drive, another user's machine, etc).

    This wrapper does not reimplement any of the checks - doctor.py remains
    the single source of truth for what "healthy" means. This script only
    finds Python and forwards to it, then forwards doctor.py's exit code
    back to the caller (so `if (doctor.ps1) { ... }` style scripting works).

.PARAMETER Json
    Forward --json to doctor.py for a machine-readable report.

.PARAMETER RootPath
    Forward --root <path> to doctor.py to check a tree other than this
    script's own directory.

.EXAMPLE
    .\doctor.ps1

.EXAMPLE
    .\doctor.ps1 -Json
#>

param(
    [switch]$Json,
    [string]$RootPath
)

$ErrorActionPreference = "Stop"

# Resolve doctor.py relative to THIS script's location, not the caller's
# current working directory - so it works when double-clicked, run from
# another folder, or copied to a different drive letter/path.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DoctorPy = Join-Path $ScriptDir "doctor.py"

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " sci-toolkit doctor (PowerShell wrapper)" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $DoctorPy)) {
    Write-Host "[FAIL] doctor.py not found next to this script: $DoctorPy" -ForegroundColor Red
    exit 1
}

# Find a Python interpreter: prefer the Windows `py` launcher, then
# `python`, then `python3`. Do not assume any specific install path.
$PythonCmd = $null
$PythonArgsPrefix = @()

if (Get-Command "py" -ErrorAction SilentlyContinue) {
    $PythonCmd = "py"
    $PythonArgsPrefix = @("-3")
} elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} elseif (Get-Command "python3" -ErrorAction SilentlyContinue) {
    $PythonCmd = "python3"
}

if (-not $PythonCmd) {
    Write-Host "[FAIL] No Python interpreter found on PATH (tried: py, python, python3)." -ForegroundColor Red
    Write-Host "       Install Python 3.10+ from https://www.python.org/downloads/ and re-run." -ForegroundColor Yellow
    exit 1
}

$DoctorArgs = @($DoctorPy)
if ($Json) { $DoctorArgs += "--json" }
if ($RootPath) { $DoctorArgs += @("--root", $RootPath) }

$FullArgs = $PythonArgsPrefix + $DoctorArgs

Write-Host "Using interpreter: $PythonCmd $($PythonArgsPrefix -join ' ')" -ForegroundColor DarkGray
Write-Host ""

& $PythonCmd @FullArgs
$ExitCode = $LASTEXITCODE

exit $ExitCode
