$ErrorActionPreference='Continue'
$cfg=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$root=[string]$cfg.external_root
Write-Host 'Talep Kontrol - ag kaynak testi' -ForegroundColor Cyan
@('1-ZMM048','2-MB51','3-MB52','4-Keşifler','5-Tanımlar','6-ZMM098') | ForEach-Object {
  $path=Join-Path $root $_
  $ok=Test-Path -LiteralPath $path -PathType Container
  Write-Host ("{0}: {1}" -f $(if ($ok) {'ERISIM VAR'} else {'ERISIM YOK'}),$path)
  if ($ok) {
    $count=@(Get-ChildItem -LiteralPath $path -Filter '*.csv' -File -ErrorAction SilentlyContinue).Count
    Write-Host ("    CSV adedi: {0}" -f $count)
  }
}
$parent=[string]$cfg.corporate_document_root
if(-not $parent){ $parent=Split-Path -Parent $root }
Write-Host 'Ust ortak belge alani:' $parent
@('2-MB51','3-MB52','5-ZMM98','7-ZMM048') | ForEach-Object {
  $path=Join-Path $parent $_
  $ok=Test-Path -LiteralPath $path -PathType Container
  Write-Host ("{0}: {1}" -f $(if ($ok) {'ERISIM VAR'} else {'ERISIM YOK'}),$path)
}
$db=[string]$cfg.shared_record_root
Write-Host 'Merkezi kayit klasoru:' $db
Write-Host ('Mevcut: '+(Test-Path -LiteralPath $db -PathType Container))
Write-Host 'Klasor mevcut degilse veya yazma izni yoksa kesin kayitlar devre disi kalmalidir.'
Write-Host 'Bu kontrol dosya yazmaz veya klasor olusturmaz.'
