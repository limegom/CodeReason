[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Compose is required for the full stack. Use the SQLite host instructions in README.md when Docker is unavailable."
}

docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose is unavailable. Use the SQLite host instructions in README.md."
}

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created .env from safe local defaults; add OPENAI_API_KEY only for live AI analysis."
}

Write-Warning "CodeReason is an unauthenticated local single-user MVP. Keep ports 3000 and 8000 on loopback."

docker compose build sandbox
if ($LASTEXITCODE -ne 0) { throw "The fixed sandbox image failed to build." }

docker compose up --build --remove-orphans
if ($LASTEXITCODE -ne 0) { throw "The CodeReason stack exited with an error." }
