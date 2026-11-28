param([Parameter(Mandatory=$true)][string]$State)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
$cache=Join-Path $env:LOCALAPPDATA 'TalepKontrol\WebView2SDK'
$version='1.0.4314.35'
$packageHash='90778deb1b77e36292828b4b5833c9255c27533f40e0ddd55891ae718944edc4'
# Match the host PowerShell process, including an x86 process on a 64-bit OS.
$arch=if([IntPtr]::Size -eq 4){'x86'}elseif($env:PROCESSOR_ARCHITECTURE -eq 'ARM64'){'arm64'}else{'x64'}
$dest=Join-Path (Join-Path $cache $version) $arch
$expected=@{
 'Microsoft.Web.WebView2.Core.dll'='acdd517b951829f763d1255f32df1e6a936cb8623a7ebff6b8b24172dede6bd6'
 'Microsoft.Web.WebView2.WinForms.dll'='c66437f80886aecf074804b61af4cc10ad90a95310c8e0a717f31ea377c26b03'
 'WebView2Loader.dll'=@{x64='d3fce90bdeecb08596e377dea6a316354dd8949e32ff09b89d51be00c14e21b6';x86='1d348d3c0a5cb0d985389b68a0fd9bf966c2aed65f5e44bbc0233739b7a57f9e';arm64='05429881d918fd64a3fe4955155c1af79e66d7b7d944034467874f420bc2265a'}[$arch]
}
function Test-Sdk([string]$Folder) {
 foreach($name in $expected.Keys){
  $path=Join-Path $Folder $name
  if(!(Test-Path -LiteralPath $path -PathType Leaf)){return $false}
  if((Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant() -ne $expected[$name]){return $false}
 }
 return $true
}
$zip=$null;$stage=$null;$backup=$null
try {
 if(!(Test-Sdk $dest)){
  New-Item -ItemType Directory -Force -Path $cache | Out-Null
  $id=[guid]::NewGuid().ToString('N')
  $zip=Join-Path $cache ('.package-'+$id+'.zip')
  $stage=Join-Path $cache ('.stage-'+$id)
  $local=Join-Path $root ('_runtime_packages\Microsoft.Web.WebView2.'+$version+'.nupkg')
  if(Test-Path -LiteralPath $local -PathType Leaf){
   Copy-Item -LiteralPath $local -Destination $zip
  }else{
   $url='https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/'+$version+'/microsoft.web.webview2.'+$version+'.nupkg'
   try{[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12}catch{}
   Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip -TimeoutSec 150
  }
  if((Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant() -ne $packageHash){throw 'WebView2 paketinin SHA-256 bilgisi uyusmuyor.'}
  Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
  $prepared=Join-Path $stage 'prepared'
  New-Item -ItemType Directory -Path $prepared -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $stage 'lib\net462\Microsoft.Web.WebView2.Core.dll') -Destination $prepared
  Copy-Item -LiteralPath (Join-Path $stage 'lib\net462\Microsoft.Web.WebView2.WinForms.dll') -Destination $prepared
  Copy-Item -LiteralPath (Join-Path $stage ('build\native\'+$arch+'\WebView2Loader.dll')) -Destination $prepared
  if(!(Test-Sdk $prepared)){throw 'WebView2 dosyalarinin butunlugu dogrulanamadi.'}
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
  if(Test-Path -LiteralPath $dest){
   $backup=Join-Path $cache ('.backup-'+$id)
   Move-Item -LiteralPath $dest -Destination $backup
  }
  try{Move-Item -LiteralPath $prepared -Destination $dest}
  catch{if($backup -and !(Test-Path -LiteralPath $dest)){Move-Item -LiteralPath $backup -Destination $dest;$backup=$null};throw}
 }
 if(!(Test-Sdk $dest)){throw 'WebView2 yerel bilesenleri dogrulanamadi.'}
 Set-Content -LiteralPath $State -Value ('OK|'+$dest) -Encoding UTF8
 if($backup){Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue}
 exit 0
}catch{
 Set-Content -LiteralPath $State -Value ('FAILED|'+$_.Exception.Message) -Encoding UTF8
 exit 1
}finally{
 if($zip){Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue}
 if($stage){Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue}
}
