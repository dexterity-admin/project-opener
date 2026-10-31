<#
.SYNOPSIS
  Publish site/ (the landing page) to the public showcase repository.

  GitHub Free does not serve Pages from private repositories, so the landing page
  lives in a second, PUBLIC repo that contains nothing but the static site:
      https://github.com/dexterity-admin/project-opener-site
      https://dexterity-admin.github.io/project-opener-site/

  This script copies site/ into a clone of that repo and pushes; its own Pages
  workflow deploys it. Run it after editing anything under site/.

.EXAMPLE
  .\tools\publish_site.ps1 -Message "Landing: update feature copy"
#>
param(
    [string]$Repo = "dexterity-admin/project-opener-site",
    [string]$Message = "Update landing page from project-opener/site"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$work = Join-Path ([System.IO.Path]::GetTempPath()) "project-opener-site-publish"
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
gh repo clone $Repo $work -- --quiet
Get-ChildItem $work -Force | Where-Object { $_.Name -notin @(".git", ".github") } | Remove-Item -Recurse -Force
Copy-Item (Join-Path $root "site\*") $work -Recurse -Force
Push-Location $work
try {
    git add -A
    if (-not (git status --porcelain)) { Write-Host "site is already up to date"; return }
    git commit -q -m $Message
    git push -q
    Write-Host "published: https://dexterity-admin.github.io/project-opener-site/"
} finally { Pop-Location }
