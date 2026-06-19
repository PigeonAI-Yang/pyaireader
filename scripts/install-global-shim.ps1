param(
    [string]$InstallDir = (Join-Path $env:USERPROFILE ".local\bin"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not $PSScriptRoot) {
    throw "Cannot locate script directory."
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PyprojectPath = Join-Path $RepoRoot "pyproject.toml"
if (-not (Test-Path -LiteralPath $PyprojectPath)) {
    throw "Cannot locate pyproject.toml from script directory: $PSScriptRoot"
}

$UvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $UvCommand) {
    $DefaultUv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (Test-Path -LiteralPath $DefaultUv) {
        $UvPath = $DefaultUv
    } else {
        throw "uv was not found. Install uv first, then rerun this script."
    }
} else {
    $UvPath = $UvCommand.Source
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$ShimPath = Join-Path $InstallDir "pyaireader.cmd"

if ((Test-Path -LiteralPath $ShimPath) -and (-not $Force)) {
    $Answer = Read-Host "pyaireader.cmd already exists at $ShimPath. Overwrite? [y/N]"
    if ($Answer -notin @("y", "Y", "yes", "YES")) {
        Write-Host "Canceled. Existing shim was not changed."
        exit 1
    }
}

$ShimBody = @"
@echo off
"$UvPath" --directory "$RepoRoot" run pyaireader %*
"@

Set-Content -LiteralPath $ShimPath -Value $ShimBody -Encoding ASCII

Write-Host "Installed pyaireader shim:"
Write-Host "  $ShimPath"
Write-Host ""
Write-Host "Try it from any directory:"
Write-Host "  pyaireader read `"https://example.com`" --pretty"
Write-Host "  pyaireader inspect `"https://example.com`" --pretty"
Write-Host ""

$PathEntries = ($env:Path -split ";") | ForEach-Object { $_.TrimEnd("\") }
$InstallDirForCompare = (Resolve-Path $InstallDir).Path.TrimEnd("\")
if ($PathEntries -notcontains $InstallDirForCompare) {
    Write-Host "Add this directory to your user PATH if pyaireader is not found:"
    Write-Host "  $InstallDirForCompare"
}
