param(
  [switch]$CleanInstall
)
$ErrorActionPreference='Stop'
$Source=Split-Path -Parent $MyInvocation.MyCommand.Path
$Target=Join-Path $env:LOCALAPPDATA 'Programs\TalepKontrol'
$UserRoot=Join-Path $env:LOCALAPPDATA 'TalepKontrol'
if (!(Test-Path (Join-Path $Source 'server.py'))) { throw 'Uygulama paket dosyalari eksik.' }

function Stop-TalepServices {
  foreach ($port in 8765..8769) {
    try {
      $req=[System.Net.HttpWebRequest]::Create("http://127.0.0.1:$port/api/health")
      $req.Timeout=400
      $resp=$req.GetResponse()
      $reader=New-Object IO.StreamReader($resp.GetResponseStream())
      $body=$reader.ReadToEnd(); $reader.Close(); $resp.Close()
      if ($body -notmatch 'Talep Kontrol') { continue }
      Write-Host "Servis kapatiliyor: $port"
      $stop=[System.Net.HttpWebRequest]::Create("http://127.0.0.1:$port/api/shutdown")
      $stop.Method='POST'; $stop.Timeout=1500; $stop.ContentLength=0
      try { $stop.GetResponse().Close() } catch {}
    } catch {}
  }
  Start-Sleep -Milliseconds 600
}

function Remove-TreeRetry([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path) -or !(Test-Path -LiteralPath $Path)) { return }
  for ($i=0; $i -lt 5; $i++) {
    try {
      Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
        try { $_.Attributes='Normal' } catch {}
      }
      Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
      Write-Host "Silindi: $Path"
      return
    } catch {
      Start-Sleep -Milliseconds (400*($i+1))
      if ($i -eq 4) { Write-Host "Silinemedi: $Path | $($_.Exception.Message)" -ForegroundColor Yellow }
    }
  }
}

if ((Test-Path $Target) -or (Test-Path $UserRoot)) {
  if (-not $CleanInstall) {
    Write-Host '[DURDURULDU] Kurulum veya yerel veri mevcut.' -ForegroundColor Yellow
    Write-Host "Kurulum: $Target"
    Write-Host "Yerel veri: $UserRoot"
    Write-Host 'Tam temiz kurulum icin: .\KURULUM.ps1 -CleanInstall'
    Write-Host 'veya Talep_Kontrol.exe icinden "Temiz kurulum" secin.'
    exit 8
  }
  Write-Host 'Temiz kurulum: eski surum ve yerel veriler siliniyor...' -ForegroundColor Cyan
  Stop-TalepServices
  Remove-TreeRetry $Target
  $programs=Split-Path $Target -Parent
  Get-ChildItem -LiteralPath $programs -Force -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -like 'TalepKontrol*' -or $_.Name -like '.TalepKontrol*'
  } | ForEach-Object { Remove-TreeRetry $_.FullName }
  Remove-TreeRetry $UserRoot
  $link=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Talep Kontrol.lnk'
  if (Test-Path -LiteralPath $link) { Remove-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue }
}

Write-Host 'Talep Kontrol - temiz kullanici kurulumu' -ForegroundColor Cyan
$parent=Split-Path $Target -Parent
New-Item -ItemType Directory -Path $parent -Force | Out-Null
$stage=Join-Path $parent ('TalepKontrol-YUKLE-'+[guid]::NewGuid().ToString('N').Substring(0,10))
try {
  New-Item -ItemType Directory -Path $stage | Out-Null
  Get-ChildItem -LiteralPath $Source -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $stage -Recurse -Force }
  if (!(Test-Path (Join-Path $stage 'config.json'))) { throw 'Kurulum oncesi paket kontrolu basarisiz.' }
  Move-Item -LiteralPath $stage -Destination $Target
  $link=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Talep Kontrol.lnk'
  $wsh=New-Object -ComObject WScript.Shell
  $shortcut=$wsh.CreateShortcut($link)
  $shortcut.TargetPath=Join-Path $Target 'BASLAT.vbs'
  $shortcut.WorkingDirectory=$env:LOCALAPPDATA
  $shortcut.IconLocation=(Join-Path $Target 'assets\brand\talep-kontrol.ico')+',0'
  $shortcut.Description='Talep Kontrol'
  $shortcut.Save()
  Write-Host 'Kurulum basarili. Masaustundeki Talep Kontrol kisayolunu kullanin.' -ForegroundColor Green
  Write-Host 'Kurulum:' $Target
  Write-Host 'Not: Merkezi ag erisimi ve Python runtime testi sirket ortaminda yapilmalidir.'
} finally {
  if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
