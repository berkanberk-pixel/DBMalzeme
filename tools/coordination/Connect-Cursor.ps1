param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference='Stop'
$settings=Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
$env:CURSOR_CONFIG_DIR=$settings.cursor_config_dir
Remove-Item Env:NO_OPEN_BROWSER -ErrorAction SilentlyContinue
Write-Host 'Cursor terminal ajani icin hesap girisi aciliyor.'
Write-Host 'Normal tarayicinizda hesabinizi secin ve CLI erisimini onaylayin.'
Write-Host 'Cursor uygulamasini yeniden indirmeniz gerekmiyor.'
& $settings.cursor_node $settings.cursor_index login
$statusOutput=& $settings.cursor_node $settings.cursor_index status --format json
try {
    $status=$statusOutput | ConvertFrom-Json
    if ($status.isAuthenticated) {
        Write-Host 'Cursor hesabi baglandi. Acik koordinasyon servisi baglantiyi otomatik gorecek.' -ForegroundColor Green
    } else {
        Write-Warning 'Giris henuz tamamlanmadi. Bu penceredeki hata metnini paylasabilirsiniz; parola veya anahtar paylasmayin.'
    }
} catch {
    Write-Warning 'Hesap durumu okunamadi. Giris sonucu koordinasyon panelinden kontrol edilebilir.'
}
