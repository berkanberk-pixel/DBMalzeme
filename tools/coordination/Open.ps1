param([Parameter(Mandatory=$true)][string]$Config)
$settings = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
if (-not $settings.port) { $settings | Add-Member -NotePropertyName port -NotePropertyValue 8765 -Force }
$token = (Get-Content -LiteralPath (Join-Path $settings.state_dir 'service.token') -Raw).Trim()
# Fragment is not sent to HTTP logs. The page moves it to sessionStorage then removes it.
try {
    Start-Process "http://127.0.0.1:$($settings.port)/#token=$([uri]::EscapeDataString($token))" -ErrorAction Stop
} catch {
    Write-Warning 'Tarayıcı bu ortamdan açılamadı. KOORDINASYON_BASLAT.cmd dosyasını kendi Windows oturumunuzdan çalıştırın.'
}
