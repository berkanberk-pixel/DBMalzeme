param([switch]$Quiet)
# Compatibility check. Installation is handled by AUTO_BASLAT.ps1 before the GUI.
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
try {
    $cfg=Get-Content -LiteralPath (Join-Path $Root 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $manifest=Join-Path ([string]$cfg.update_share) 'manifest.json'
    if (!(Test-Path -LiteralPath $manifest -PathType Leaf)) {
        if (!$Quiet) { Write-Host 'Aktif yayin bulunamadi; kurulu uygulama kullanilacak.' }
        exit 0
    }
    $remote=Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
    if (!$Quiet) { Write-Host ('Aktif yayin: '+[string]$remote.release_id+' (kontrol otomatik yapilir)') }
} catch { if (!$Quiet) { Write-Warning $_.Exception.Message } }
exit 0
