[CmdletBinding()]
param(
    [switch]$RestartServices,
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$publicHost = 'tradelens.othla.in'

function Wait-ForLocalUrl {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Name
    )

    for ($attempt = 1; $attempt -le 15; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Host "$Name is ready: $Url" -ForegroundColor Green
                return
            }
        } catch {
            if ($attempt -eq 15) {
                throw "$Name did not become available at $Url. Start it with .\\restart-services.ps1, then try again."
            }
        }
        Start-Sleep -Seconds 2
    }
}

if ($RestartServices) {
    & (Join-Path $projectRoot 'restart-services.ps1')
}

Wait-ForLocalUrl -Url 'http://127.0.0.1:5004' -Name 'TradeLens frontend'
Wait-ForLocalUrl -Url 'http://127.0.0.1:9004/api/health' -Name 'TradeLens API'

$cloudflared = Get-Command cloudflared -ErrorAction Stop
$tunnelNames = & $cloudflared.Source tunnel list --output json | ConvertFrom-Json
$tunnel = $tunnelNames | Where-Object { $_.name -eq 'tradelens' } | Select-Object -First 1
if ($null -eq $tunnel) {
    throw "The Cloudflare tunnel named 'tradelens' was not found for this Cloudflare account."
}

if ($ValidateOnly) {
    Write-Host "TradeLens is ready to connect: https://$publicHost -> http://localhost:5004" -ForegroundColor Green
    return
}

Write-Host "Connecting https://$publicHost to http://localhost:5004. Press Ctrl+C to stop this TradeLens connector." -ForegroundColor Green
$tunnelToken = (& $cloudflared.Source tunnel token tradelens).Trim()
if ([string]::IsNullOrWhiteSpace($tunnelToken)) {
    throw "Cloudflare did not return a connector token for the 'tradelens' tunnel."
}

try {
    & $cloudflared.Source tunnel run --token $tunnelToken
} finally {
    Remove-Variable -Name tunnelToken -ErrorAction SilentlyContinue
}
