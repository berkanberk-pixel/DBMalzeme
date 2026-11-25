# Talep Kontrol - Salt okunur baglanti ve indeks kontrolu
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
$configPath=Join-Path $root 'config.json'
try {
    $cfg=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Host 'config.json okunamiyor veya gecersiz JSON.' -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
Write-Host 'Talep Kontrol - baglanti kontrolu' -ForegroundColor Cyan
Write-Host ('Kaynak: '+[string]$cfg.external_root)
Write-Host ('Kaynak erisimi: '+(Test-Path -LiteralPath $cfg.external_root -PathType Container))
foreach($dir in @('1-ZMM048','2-MB51','3-MB52','4-Keşifler','5-Tanımlar')) {
    $path=Join-Path ([string]$cfg.external_root) $dir
    Write-Host ("$dir : " + (Test-Path -LiteralPath $path -PathType Container))
}
Write-Host ('Merkezi kayit: '+[string]$cfg.shared_record_root)
Write-Host ('Kayit erisimi: '+(Test-Path -LiteralPath $cfg.shared_record_root -PathType Container))
Write-Host ('Yayin konumu: '+[string]$cfg.update_share)
Write-Host ('Yayin erisimi: '+(Test-Path -LiteralPath $cfg.update_share -PathType Container))
Write-Host ('Merkezi yazma acik: '+[string]$cfg.shared_writes_enabled)
$indexRoot=Join-Path $env:LOCALAPPDATA 'TalepKontrol\Index'
Write-Host ('Yerel indeks: '+$indexRoot)
$pointer=Join-Path $indexRoot 'ACTIVE_BUILD.json'
Write-Host ('Aktif indeks isaretcisi: '+(Test-Path -LiteralPath $pointer -PathType Leaf))
if(Test-Path -LiteralPath $pointer -PathType Leaf) {
    try { $active=Get-Content -LiteralPath $pointer -Raw -Encoding UTF8 | ConvertFrom-Json
          Write-Host ('Indeks olusturma zamani: '+[string]$active.created_at) } catch {}
}
Write-Host 'Bu komut hicbir veriyi silmez veya degistirmez.' -ForegroundColor DarkGray
