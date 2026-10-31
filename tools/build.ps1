<#
.SYNOPSIS
  Build Project Opener end-to-end on Windows: tests -> icon -> PyInstaller -> Inno Setup -> manifest.

.EXAMPLE
  .\tools\build.ps1                 # full build into dist\
  .\tools\build.ps1 -SkipTests      # faster iteration
  .\tools\build.ps1 -Python .\.venv\Scripts\python.exe

  Requires: a Python 3.11+ environment with requirements-dev.txt installed, and
  Inno Setup 6/7 (ISCC.exe) either on PATH or in one of the usual folders.
#>
param(
    [string]$Python = "python",
    [switch]$SkipTests,
    [switch]$SkipInstaller
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (& $Python -c "import project_opener; print(project_opener.__version__)").Trim()
Write-Host "== Project Opener $version ==" -ForegroundColor Cyan

if (-not $SkipTests) {
    Write-Host "-- tests" -ForegroundColor Cyan
    & $Python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw "tests failed" }
}

Write-Host "-- icon + version resource" -ForegroundColor Cyan
& $Python tools\build_icon.py
& $Python tools\version_info.py

Write-Host "-- PyInstaller" -ForegroundColor Cyan
if (Test-Path dist\ProjectOpener) { Remove-Item -Recurse -Force dist\ProjectOpener }
& $Python -m PyInstaller project_opener.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "-- smoke run of the frozen exe" -ForegroundColor Cyan
& dist\ProjectOpener\ProjectOpener.exe --version
if ($LASTEXITCODE -ne 0) { throw "frozen exe failed to start" }

if (-not $SkipInstaller) {
    $iscc = Get-Command iscc -ErrorAction SilentlyContinue
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\InnoSetup7\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $isccPath = if ($iscc) { $iscc.Source } else { $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1 }
    if (-not $isccPath) { throw "ISCC.exe (Inno Setup) not found" }
    Write-Host "-- Inno Setup ($isccPath)" -ForegroundColor Cyan
    & $isccPath "installer\ProjectOpener.iss" "/DAppVersion=$version" /Qp
    if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }
    & $Python tools\make_manifest.py "dist\ProjectOpener-Setup-$version.exe"
}

Write-Host "-- portable zip" -ForegroundColor Cyan
$zip = "dist\ProjectOpener-Portable-$version.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path dist\ProjectOpener\* -DestinationPath $zip -CompressionLevel Optimal
Get-ChildItem dist -File | Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}} | Format-Table -AutoSize
Write-Host "done" -ForegroundColor Green
