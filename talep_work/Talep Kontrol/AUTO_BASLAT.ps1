# Talep Kontrol - GUI'yi acmadan once otomatik, kontrollu guncelleme.
# Windows PowerShell 5.1 + mevcut Python; CMD penceresi acmaz.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if ([string]::IsNullOrWhiteSpace($LocalAppData)) {
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show('Windows, oturum açan kullanıcının yerel uygulama klasörünü bulamadı.', 'Talep Kontrol')
    exit 91
}
$env:LOCALAPPDATA = $LocalAppData
$UserRoot = Join-Path $LocalAppData 'TalepKontrol'
$LogDir = Join-Path $UserRoot 'Guncelleme'
$WorkDir = Join-Path $UserRoot 'Temp'
$LogFile = Join-Path $LogDir 'baslatma.log'
function Log([string]$Text) {
    try { Add-Content -LiteralPath $LogFile -Value ((Get-Date -Format s)+' | '+$Text) -Encoding UTF8 } catch {}
}
function Get-PythonPath {
    foreach ($tag in @('amd64','arm64','win32')) {
        $candidate = Join-Path $Root ("_runtime\python313-$tag\python.exe")
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    $privatePython = Join-Path $LocalAppData 'Programs\TalepKontrol\Python313\python.exe'
    if (Test-Path -LiteralPath $privatePython -PathType Leaf) { return $privatePython }
    foreach ($ver in @('315','314','313','312','311','310')) {
        $candidate = Join-Path $env:LOCALAPPDATA ("Programs\Python\Python$ver\python.exe")
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    foreach ($cmd in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
        if ($cmd.Source -and $cmd.Source -notlike '*\WindowsApps\*') { return [string]$cmd.Source }
    }
    return $null
}
function Launch-Workspace {
    $path = Join-Path $Root 'START_GUI.ps1'
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw 'START_GUI.ps1 bulunamadi.' }
    # The app root may have been atomically replaced. Start the GUI from the
    # new path, but do not keep the working directory pinned inside that root.
    Set-Location -LiteralPath $WorkDir
    Log ('GUI başlatılıyor: '+$path)
    if ($script:TalepBackgroundCheck) {
        & $path -BackgroundUpdatePlan $script:TalepBackgroundCheck
    } else { & $path }
}
try {
    New-Item -ItemType Directory -Force -Path $LogDir, $WorkDir | Out-Null
    $env:TEMP = $WorkDir
    $env:TMP = $WorkDir
} catch {
    Log ('Yerel çalışma klasörü oluşturulamadı: '+$_.Exception.Message)
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show(
        "Oturum açan kullanıcının çalışma klasörü hazırlanamadı.`n$WorkDir`n$($_.Exception.Message)",
        'Talep Kontrol')
    exit 91
}
$UpdateMarker = Join-Path $LogDir 'paket_kontrolu.json'
$script:TalepBackgroundCheck = $null
$env:TALEP_UPDATE_RESULT = 'yerel_baslatma'
try {
    $install = Join-Path $env:LOCALAPPDATA 'Programs\TalepKontrol'
    $isInstalled = [string]::Equals(
        [IO.Path]::GetFullPath($Root).TrimEnd('\'),
        [IO.Path]::GetFullPath($install).TrimEnd('\'),
        [StringComparison]::OrdinalIgnoreCase
    )
    if ($isInstalled) {
        $env:TALEP_UPDATE_RESULT = 'kontrol_basarisiz'
        $cfgPath = Join-Path $Root 'config.json'
        $cfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cfg.auto_install_updates -eq $true) {
            $shareActive = [string]$cfg.update_share
            $updater = Join-Path $Root 'otomatik_guncelleyici.py'
            $python = Get-PythonPath
            if ($python -and (Test-Path -LiteralPath $updater -PathType Leaf) -and
                $shareActive.EndsWith('\Aktif',[StringComparison]::OrdinalIgnoreCase)) {
                $shareRoot = Split-Path -Parent $shareActive
                $statusFile = Join-Path $WorkDir ('update-'+[guid]::NewGuid().ToString('N')+'.json')
                $args = @('"'+$updater+'"','--share-root','"'+$shareRoot+'"',
                          '--install-dir','"'+$Root+'"','--user-data','"'+$UserRoot+'"',
                          '--status-file','"'+$statusFile+'"')
                $seen = $null
                if (Test-Path -LiteralPath $UpdateMarker -PathType Leaf) {
                    try { $seen = Get-Content -LiteralPath $UpdateMarker -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
                }
                if ($seen.result -eq 'guncelleme_hazir') {
                    Remove-Item -LiteralPath $UpdateMarker -Force -ErrorAction SilentlyContinue
                    Set-Location -LiteralPath $WorkDir
                    $process = $null
                    try {
                        $process = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $WorkDir `
                            -WindowStyle Hidden -Wait -PassThru
                        if ($process.ExitCode -eq 0 -and (Test-Path -LiteralPath $statusFile -PathType Leaf)) {
                            $status = Get-Content -LiteralPath $statusFile -Raw -Encoding UTF8 | ConvertFrom-Json
                            if ($status.result -in @('guncellendi','guncel','yayin_yok','servis_acik')) {
                                $env:TALEP_UPDATE_RESULT = $status.result
                            }
                        }
                    } finally {
                        if ($process) { $process.Dispose() }
                        Remove-Item -LiteralPath $statusFile -Force -ErrorAction SilentlyContinue
                    }
                    # A successful install may have replaced the updater. Its next launch probes again.
                    if ($env:TALEP_UPDATE_RESULT -ne 'guncellendi') {
                        $script:TalepBackgroundCheck = @{Python=$python; Args=$args; Status=$statusFile; WorkDir=$WorkDir}
                    }
                } else {
                    $env:TALEP_UPDATE_RESULT = ''
                    $script:TalepBackgroundCheck = @{Python=$python; Args=$args; Status=$statusFile; WorkDir=$WorkDir}
                }
            } else { Log 'Guncelleyici icin Python veya merkezi yayin adresi hazir degil; mevcut uygulama aciliyor.' }
        } else { $env:TALEP_UPDATE_RESULT = 'otomatik_kapali' }
    }
} catch { Log ('Guncelleme kontrolu: '+$_.Exception.Message) }
try { Launch-Workspace }
catch {
    $failure = $_
    Log ('GUI açılış hatası: '+$failure.Exception.ToString())
    Log ('PowerShell: '+$failure.FullyQualifiedErrorId+' | '+$failure.InvocationInfo.PositionMessage)
    $message = "Talep Kontrol açılamadı.`n`n$($failure.Exception.Message)`n`nGünlük: $LogFile"
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        $message,
        'Talep Kontrol', [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    exit 91
}
