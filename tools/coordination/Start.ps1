param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference = 'Stop'
$configPath = (Resolve-Path -LiteralPath $Config).Path
$settings = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
if (-not $settings.port) { $settings | Add-Member -NotePropertyName port -NotePropertyValue 8765 -Force }
$stateDir = $settings.state_dir
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
try {
    $existing = Invoke-RestMethod -Uri "http://127.0.0.1:$($settings.port)/health" -TimeoutSec 2
    if ($existing.service -eq 'talep-coordination') {
        Write-Output 'Koordinasyon servisi zaten çalışıyor.'
        return
    }
} catch { }
$scriptPath = Join-Path $PSScriptRoot 'coordinator.py'
$arguments = @('-u', ('"' + $scriptPath + '"'), '--config', ('"' + $configPath + '"'))
$service = Start-Process -FilePath $settings.python -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $stateDir 'service.log') -RedirectStandardError (Join-Path $stateDir 'service-error.log')
for ($attempt=0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 250
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$($settings.port)/health" -TimeoutSec 1
        if ($health.service -eq 'talep-coordination') { break }
    } catch { }
}
if (-not $health -or $health.service -ne 'talep-coordination') {
    throw 'Servis hazır olmadı. state_dir içindeki service-error.log dosyasını kontrol edin.'
}
Write-Output "Koordinasyon servisi başlatıldı (PID $($service.Id))."
