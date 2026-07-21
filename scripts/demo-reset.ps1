[CmdletBinding()]
param(
    [ValidateSet("fixture", "live")]
    [string]$Mode = "fixture",
    [string]$ApiBaseUrl = $(if ($env:API_BASE_URL) { $env:API_BASE_URL } else { "http://localhost:8000/api" })
)

$ErrorActionPreference = "Stop"
$Provenance = $Mode.ToUpperInvariant()
$Body = @{ provenance = $Provenance } | ConvertTo-Json -Compress

$Response = Invoke-RestMethod `
    -Method Post `
    -Uri "$($ApiBaseUrl.TrimEnd('/'))/demo/reset" `
    -ContentType "application/json" `
    -Body $Body

Write-Host "Demo reset mode requested: $Provenance"
Write-Host "Persisted provenance: $($Response.provenance); execution jobs queued: $($Response.execution_jobs_queued)"
