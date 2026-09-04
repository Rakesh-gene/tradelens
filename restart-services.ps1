[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot

function Get-ListeningProcessIds {
    param([int]$Port)

    $pattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    $processIds = foreach ($line in (netstat -ano -p tcp)) {
        if ($line -match $pattern) {
            [int]$Matches[1]
        }
    }
    return @($processIds | Select-Object -Unique)
}

function Stop-ProcessOnPort {
    param([int]$Port)

    foreach ($processId in (Get-ListeningProcessIds -Port $Port)) {
        Write-Host "Stopping PID $processId on port $Port..."
        & taskkill.exe /F /PID $processId | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not stop PID $processId on port $Port. Run this script from an Administrator PowerShell."
        }
    }

    for ($attempt = 0; $attempt -lt 5 -and (Get-ListeningProcessIds -Port $Port); $attempt++) {
        Start-Sleep -Seconds 1
    }
    if (Get-ListeningProcessIds -Port $Port) {
        throw "Port $Port is still occupied after stopping its listener."
    }
}

Stop-ProcessOnPort -Port 5004
Stop-ProcessOnPort -Port 9004

$backendDirectory = Join-Path $projectRoot 'src\backend'
$frontendDirectory = Join-Path $projectRoot 'src\frontend'
$backendPython = Join-Path $backendDirectory '.venv\Scripts\python.exe'
if (Test-Path $backendPython) {
    $backendProcess = Start-Process -FilePath $backendPython -ArgumentList 'app.py' `
        -WorkingDirectory $backendDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $projectRoot 'backend.log') `
        -RedirectStandardError (Join-Path $projectRoot 'backend-error.log')
} else {
    $backendProcess = Start-Process -FilePath 'py.exe' -ArgumentList '-3.11', 'app.py' `
        -WorkingDirectory $backendDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $projectRoot 'backend.log') `
        -RedirectStandardError (Join-Path $projectRoot 'backend-error.log')
}

$frontendProcess = Start-Process -FilePath 'npm.cmd' -ArgumentList 'run', 'dev' `
    -WorkingDirectory $frontendDirectory -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $projectRoot 'frontend.log') `
    -RedirectStandardError (Join-Path $projectRoot 'frontend-error.log')

$backendProcess.Id | Set-Content -NoNewline (Join-Path $projectRoot '.backend.pid')
$frontendProcess.Id | Set-Content -NoNewline (Join-Path $projectRoot '.frontend.pid')
Start-Sleep -Seconds 2
if ($backendProcess.HasExited -or $frontendProcess.HasExited) {
    throw 'A service exited during startup. See the *-error.log files for details.'
}
Write-Host 'TradeLens restarted: backend http://127.0.0.1:9004, frontend http://127.0.0.1:5004'
