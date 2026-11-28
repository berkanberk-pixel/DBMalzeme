param([Parameter(Mandatory=$true)][string]$Config)
$settings = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
if (-not $settings.port) { $settings | Add-Member -NotePropertyName port -NotePropertyValue 8765 -Force }
$token = (Get-Content -LiteralPath (Join-Path $settings.state_dir 'service.token') -Raw).Trim()
Invoke-RestMethod -Uri "http://127.0.0.1:$($settings.port)/api/shutdown" -Method Post -Headers @{Authorization="Bearer $token"} -ContentType 'application/json' -Body '{}' | Out-Null
Write-Output 'Servise durma isteği gönderildi; çalışan ajan süreci de sonlandırılır.'
