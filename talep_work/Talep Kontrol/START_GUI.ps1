# Talep Kontrol Windows GUI - isolated session owner + WebView2.
param([hashtable]$BackgroundUpdatePlan)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
# Borderless, resizable native WinForms host. WM_NCHITTEST is used only for
# edge/corner resize; windows security policies and browser settings unchanged.
Add-Type -ReferencedAssemblies @('System.Windows.Forms','System.Drawing') -TypeDefinition @'
using System;
using System.Drawing;
using System.Windows.Forms;
using System.Runtime.InteropServices;
public class TalepDesktopWindow : Form {
    public bool EnableEdgeResize { get; set; }
    private const int WM_NCHITTEST = 0x0084;
    protected override void WndProc(ref Message m) {
        base.WndProc(ref m);
        if (m.Msg != WM_NCHITTEST || !EnableEdgeResize || WindowState != FormWindowState.Normal || m.Result != (IntPtr)1) return;
        Point pos = PointToClient(Cursor.Position);
        int grip = 9;
        bool left = pos.X >= 0 && pos.X < grip;
        bool right = pos.X >= ClientSize.Width-grip && pos.X < ClientSize.Width;
        bool top = pos.Y >= 0 && pos.Y < grip;
        bool bottom = pos.Y >= ClientSize.Height-grip && pos.Y < ClientSize.Height;
        if (left && top) m.Result = (IntPtr)13;
        else if (right && top) m.Result = (IntPtr)14;
        else if (left && bottom) m.Result = (IntPtr)16;
        else if (right && bottom) m.Result = (IntPtr)17;
        else if (left) m.Result = (IntPtr)10;
        else if (right) m.Result = (IntPtr)11;
        else if (top) m.Result = (IntPtr)12;
        else if (bottom) m.Result = (IntPtr)15;
    }
    [DllImport("user32.dll")] public static extern bool ReleaseCapture();
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam);
}
'@
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$TempDir = Join-Path $env:LOCALAPPDATA 'TalepKontrol\Desktop'
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
$script:SessionId = [Guid]::NewGuid().ToString('N')
$script:SessionToken = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
$script:SessionState = Join-Path $TempDir ('session-' + $script:SessionId + '.json')
$SdkState = Join-Path $TempDir ('webview-' + $script:SessionId + '.status')
$Log = Join-Path $env:TEMP 'YEDAS_TalepKontrol_STARTUP.log'
$IconFile = Join-Path $Root 'assets\brand\talep-kontrol.ico'
$LogoFile = Join-Path $Root 'assets\brand\talep-kontrol-banner.png'
$script:svcProc = $null
$script:sdkProc = $null
$script:web = $null
$script:ready = $false
$script:bootError = ''
$script:sdkPath = ''
$script:webStarted = $false
$script:started = [DateTime]::UtcNow
$script:serverPort = 0
$script:serverPid = 0
$script:closed = $false
$script:tickCount = 0
$script:loaderFrame = 0
$script:brandStream = $null
$script:detailCycle = 0
$script:statusCount = 0
$script:navigationReady = $false
$script:bootPageReady = $false
$script:uiSwapDone = $false

function New-Label([string]$txt,[int]$size,[System.Drawing.Color]$color) {
    $label=New-Object System.Windows.Forms.Label
    $label.Text=$txt
    $label.ForeColor=$color
    $label.Font=New-Object System.Drawing.Font('Segoe UI',$size,[System.Drawing.FontStyle]::Regular,[System.Drawing.GraphicsUnit]::Point)
    # Grayscale GDI+ glyph edges avoid ClearType/RGB subpixel halos
    # on a transparent window; use at native pixel scale for sharp text.
    $label.UseCompatibleTextRendering=$true
    $label.AutoSize=$false
    $label.BackColor=[Drawing.Color]::Transparent
    return $label
}
function Show-Error([string]$txt){
    $script:ready=$true
    $timer.Stop()
    try { Add-Content -LiteralPath $Log -Value ((Get-Date -Format s)+' | GUI | '+$txt) -Encoding UTF8 } catch {}
    $loading.Text='Başlatma tamamlanamadı'
    # Keep the small window readable; the complete error is preserved in the log.
    if($txt -match 'WebView2.*(Erişim engellendi|E_ACCESSDENIED|0x80070005)'){
        $detail.Text='Windows uygulama bileşenine erişim engellendi. Hata günlüğünü açarak ayrıntıları inceleyin.'
    }elseif($txt.Length -gt 135){
        $detail.Text=$txt.Substring(0,132)+'...'
    }else{$detail.Text=$txt}
    $detail.Visible=$true
    foreach($dot in $dots){$dot.Visible=$false}
    $progress.Visible=$false
    $openLog.Visible=$true
    $retry.Visible=$true
}
function Get-SessionService {
    if (!(Test-Path -LiteralPath $script:SessionState)) { return $null }
    try {
        $s = Get-Content -LiteralPath $script:SessionState -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($s.sessionId -ne $script:SessionId) { return $null }
        return $s
    } catch { return $null }
}
function Get-Health([int]$port){
    try {
        $req=[Net.HttpWebRequest]::Create('http://127.0.0.1:'+$port+'/api/health')
        $req.Timeout=750
        $resp=$req.GetResponse()
        try {
            $reader=New-Object IO.StreamReader($resp.GetResponseStream())
            try { return ($reader.ReadToEnd() | ConvertFrom-Json) } finally { $reader.Dispose() }
        } finally {$resp.Dispose()}
    } catch {return $null}
}
function Stop-OwnedProcess([int]$pidToStop,[string]$scriptName){
    if($pidToStop -le 0) {return}
    try {
        $cim=Get-CimInstance Win32_Process -Filter ('ProcessId='+$pidToStop) -ErrorAction Stop
        $cmd=[string]$cim.CommandLine
        $checkPath=Join-Path $Root $scriptName
        if ($cmd.Contains($checkPath) -and $cmd.Contains('server.py')) {
            Stop-Process -Id $pidToStop -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}
function Stop-LocalService {
    if($script:closed) {return}
    $script:closed=$true
    try {$timer.Stop()} catch {}
    $s=Get-SessionService
    if($s -and $s.port -ge 8765 -and $s.port -le 8769 -and $s.pid -gt 0){
        $port=[int]$s.port;$pidToStop=[int]$s.pid
        $h=Get-Health $port
        if($h -and $h.sessionId -eq $script:SessionId -and [int]$h.servicePid -eq $pidToStop){
            try {
                $request=[Net.HttpWebRequest]::Create('http://127.0.0.1:'+$port+'/api/shutdown')
                $request.Method='POST'
                $request.Timeout=1200
                $request.Headers.Add('X-Talep-Session-Token',$script:SessionToken)
                $response=$request.GetResponse();$response.Dispose()
            }catch{}
            # End only this session's process if graceful shutdown fails.
            $deadline=[DateTime]::UtcNow.AddSeconds(3)
            while([DateTime]::UtcNow -lt $deadline){
                try { $p=[Diagnostics.Process]::GetProcessById($pidToStop);$p.Refresh();if($p.HasExited){break} }
                catch {break}
                [System.Threading.Thread]::Sleep(120)
            }
            Stop-OwnedProcess $pidToStop 'startup_runner.py'
        } else {
            # Initialization might have been cancelled before /api/health became ready.
            # Only terminate the recorded PID if the exact packaged runner is verified.
            Stop-OwnedProcess $pidToStop 'startup_runner.py'
        }
    }
    foreach($p in @($script:svcProc,$script:sdkProc)){
        if($p){try {$p.Refresh();if(!$p.HasExited){$p.Kill()}}catch{};try{$p.Dispose()}catch{}}
    }
    foreach($path in @($script:SessionState,$SdkState)) {try {Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue} catch{}}
}
try {
    $window=New-Object TalepDesktopWindow
    $window.Text='Talep Kontrol'
    $window.StartPosition='CenterScreen'
    # Compact centered splash; ready application opens in a normal resizable window.
    $window.Width=550
    $window.Height=400
    $window.MinimumSize=New-Object System.Drawing.Size(500,370)
    # A real Windows transparency key: the compact loading form is a cut-out
    # over the desktop. All splash surfaces use this exact key color.
    # This is switched OFF before the opaque, interactive WebView workspace.
    # Near-black chroma key instead of bright magenta: no pink halos
    # from antialiased fonts against the transparency color.
    $script:splashKey=[Drawing.Color]::FromArgb(1,2,3)
    $window.BackColor=$script:splashKey
    $window.AllowTransparency=$true
    $window.TransparencyKey=$script:splashKey
    $window.FormBorderStyle=[System.Windows.Forms.FormBorderStyle]::None
    $window.KeyPreview=$true
    $window.WindowState=[System.Windows.Forms.FormWindowState]::Normal
    $window.ForeColor=[System.Drawing.Color]::White
    # The desktop window is an ordinary taskbar application, never an always-on-top overlay.
    $window.ShowInTaskbar=$true
    $window.TopMost=$false
    if(Test-Path -LiteralPath $IconFile){$window.Icon=New-Object System.Drawing.Icon($IconFile)}
    # The splash is intentionally compact. The real window MUST resize the
    # entire WebView host: explicitly calculate every container's bounds.
    # Relying on a nested TableLayoutPanel left the host at the splash size
    # on certain Windows DPI/PowerShell/WinForms combinations.
    $script:workspaceMode=$false
    # Pseudo-maximize keeps the custom borderless window INSIDE the monitor's
    # WorkingArea; unlike native Maximized it does not cover the taskbar.
    $script:workspaceExpanded=$false
    $script:restoreBounds=$null
    $window.Padding=New-Object System.Windows.Forms.Padding(0)
    $layout=New-Object System.Windows.Forms.Panel
    $layout.Dock=[System.Windows.Forms.DockStyle]::None
    $layout.Margin=New-Object System.Windows.Forms.Padding(0)
    $layout.Padding=New-Object System.Windows.Forms.Padding(0)
    $window.Controls.Add($layout)

    $hostPanel=New-Object System.Windows.Forms.Panel
    $hostPanel.Dock=[System.Windows.Forms.DockStyle]::None
    $hostPanel.Margin=New-Object System.Windows.Forms.Padding(0)
    $hostPanel.Padding=New-Object System.Windows.Forms.Padding(0)
    $layout.Controls.Add($hostPanel)

    $titleBar=New-Object System.Windows.Forms.Panel
    $titleBar.Dock=[System.Windows.Forms.DockStyle]::None
    $titleBar.Margin=New-Object System.Windows.Forms.Padding(0)
    # Flat in-app command rail (not a Windows frame or a drawn outer border).
    $titleBar.BackColor=[Drawing.Color]::FromArgb(16,45,65)
    $layout.Controls.Add($titleBar)
    $titleBar.BringToFront()
    $script:layout=$layout
    $script:hostPanel=$hostPanel
    $script:titleBar=$titleBar

    function Sync-DesktopContentBounds {
        # Native WinForms form bounds are the source of truth; never reuse
        # splash dimensions when the application transitions to its workspace.
        if (!$window -or $window.IsDisposed -or !$script:layout) { return }
        $cw=[Math]::Max(1,[int]$window.ClientSize.Width)
        $ch=[Math]::Max(1,[int]$window.ClientSize.Height)
        # No painted frame, margin or Windows-style border. The WebView fills
        # every available pixel beneath the 40 px integrated control strip.
        $lx=0; $ly=0
        $lw=$cw
        $lh=$ch
        $barHeight=if($script:workspaceMode){40}else{0}
        $hostHeight=[Math]::Max(1,$lh-$barHeight)
        $script:layout.SetBounds($lx,$ly,$lw,$lh)
        $script:titleBar.SetBounds(0,0,$lw,$barHeight)
        $script:titleBar.Visible=$script:workspaceMode
        $script:hostPanel.SetBounds(0,$barHeight,$lw,$hostHeight)
        if($script:web -and !$script:web.IsDisposed){
            if($script:workspaceMode){
                $script:web.SetBounds(0,0,$lw,$hostHeight)
            } else {
                # Keep WebView alive at usable viewport dimensions but wholly
                # OUTSIDE the splash host. The browser loader (and its scrollbar)
                # must never peek through transparent splash areas.
                $script:web.SetBounds(-2400,0,1200,800)
            }
        }
        if($splash -and !$splash.IsDisposed){
            $splash.SetBounds(0,0,$lw,$hostHeight)
        }
        if($script:workspaceMode){
            $window.BackColor=[Drawing.Color]::FromArgb(16,45,65)
        }
    }

    $captionText=New-Label 'Talep Kontrol' 11 ([Drawing.Color]::FromArgb(229,242,247))
    $captionText.Font=New-Object System.Drawing.Font('Segoe UI',11,[Drawing.FontStyle]::Bold)
    $captionText.TextAlign='MiddleLeft'
    $captionText.Left=45;$captionText.Top=0;$captionText.Height=40;$captionText.Width=390
    $titleBar.Controls.Add($captionText)
    $captionIcon=New-Object System.Windows.Forms.PictureBox
    $captionIcon.SizeMode='Zoom';$captionIcon.Left=14;$captionIcon.Top=8;$captionIcon.Width=24;$captionIcon.Height=24
    $captionIcon.BackColor=[Drawing.Color]::Transparent
    $captionIconFile=Join-Path $Root 'assets\brand\talep-kontrol.ico.png'
    if(Test-Path -LiteralPath $captionIconFile){$captionIcon.Image=[Drawing.Image]::FromFile($captionIconFile)}
    $titleBar.Controls.Add($captionIcon)

    function New-CaptionButton([string]$label,[string]$hint){
        $b=New-Object System.Windows.Forms.Button
        $b.Text=$label
        $b.Width=40;$b.Height=34
        $b.FlatStyle=[System.Windows.Forms.FlatStyle]::Flat
        $b.FlatAppearance.BorderSize=0
        $b.BackColor=[Drawing.Color]::FromArgb(16,45,65)
        $b.ForeColor=[Drawing.Color]::FromArgb(219,236,244)
        $b.Font=New-Object System.Drawing.Font('Segoe UI',12)
        $b.TabStop=$false
        $b.AccessibleName=$hint
        $b.Cursor=[System.Windows.Forms.Cursors]::Hand
        return $b
    }
    $minButton=New-CaptionButton ([string][char]0x2212) 'Simge durumuna küçült'
    $maxButton=New-CaptionButton ([string][char]0x2922) 'Büyüt / önceki boyut'
    $exitButton=New-CaptionButton ([string][char]0x00D7) 'Kapat'
    foreach($b in @($minButton,$maxButton,$exitButton)){$titleBar.Controls.Add($b)}
    $minButton.Add_Click({$window.WindowState=[System.Windows.Forms.FormWindowState]::Minimized})
    function Set-WorkspaceExpanded {
        if (!$script:workspaceMode -or $script:workspaceExpanded) { return }
        # Monitor-local WorkingArea excludes taskbars on every edge and supports
        # multi-monitor setups. Do not use FormWindowState.Maximized here.
        if ($window.WindowState -ne [System.Windows.Forms.FormWindowState]::Normal) {
            $window.WindowState=[System.Windows.Forms.FormWindowState]::Normal
        }
        $script:restoreBounds=$window.Bounds
        $work=[System.Windows.Forms.Screen]::FromControl($window).WorkingArea
        $script:workspaceExpanded=$true
        $window.Bounds=$work
        $maxButton.Text=[string][char]0x2921
        Sync-DesktopContentBounds
    }
    function Restore-WorkspaceExpanded([bool]$forDrag=$false) {
        if (!$script:workspaceExpanded) { return }
        $oldExpanded=$window.Bounds
        $previous=$script:restoreBounds
        $script:workspaceExpanded=$false
        if ($null -eq $previous -or $previous.Width -lt 500 -or $previous.Height -lt 370) {
            $available=[System.Windows.Forms.Screen]::FromControl($window).WorkingArea
            $previous=New-Object System.Drawing.Rectangle -ArgumentList @(
                [int]($available.Left+80),[int]($available.Top+50),
                [int][Math]::Min(1200,$available.Width),[int][Math]::Min(800,$available.Height))
        }
        if ($forDrag) {
            # Behave like Windows: dragging a maximized custom title bar first
            # restores the prior size under the cursor, then begins moving it.
            $cursor=[System.Windows.Forms.Cursor]::Position
            $work=[System.Windows.Forms.Screen]::FromPoint($cursor).WorkingArea
            $width=[Math]::Min([int]$previous.Width,[int]$work.Width)
            $height=[Math]::Min([int]$previous.Height,[int]$work.Height)
            $ratio=[Math]::Max(0,[Math]::Min(1,([double]($cursor.X-$oldExpanded.Left)/[Math]::Max(1,$oldExpanded.Width))))
            $grab=[int]($ratio*$width)
            $x=[Math]::Max($work.Left,[Math]::Min(($work.Right-$width),($cursor.X-$grab)))
            $y=[Math]::Max($work.Top,[Math]::Min(($work.Bottom-$height),($cursor.Y-20)))
            $previous=New-Object System.Drawing.Rectangle -ArgumentList @([int]$x,[int]$y,[int]$width,[int]$height)
        }
        $window.WindowState=[System.Windows.Forms.FormWindowState]::Normal
        $window.Bounds=$previous
        $maxButton.Text=[string][char]0x2922
        Sync-DesktopContentBounds
    }
    $script:toggleSize={
        if ($script:workspaceExpanded) {
            Restore-WorkspaceExpanded
        } else {
            Set-WorkspaceExpanded
        }
    }
    $maxButton.Add_Click({& $script:toggleSize})
    $window.Add_Resize({
        # Minimize remains native; restore/maximize is driven by our custom
        # state so native FormBorderStyle.None never hides the Windows taskbar.
        $maxButton.Text=if($script:workspaceExpanded){[string][char]0x2921}else{[string][char]0x2922}
    })
    $exitButton.Add_Click({$window.Close()})
    $minButton.Add_MouseEnter({$minButton.BackColor=[Drawing.Color]::FromArgb(49,76,96)})
    $minButton.Add_MouseLeave({$minButton.BackColor=[Drawing.Color]::FromArgb(16,45,65)})
    $maxButton.Add_MouseEnter({$maxButton.BackColor=[Drawing.Color]::FromArgb(49,76,96)})
    $maxButton.Add_MouseLeave({$maxButton.BackColor=[Drawing.Color]::FromArgb(16,45,65)})
    $exitButton.Add_MouseEnter({$exitButton.BackColor=[Drawing.Color]::FromArgb(157,66,80)})
    $exitButton.Add_MouseLeave({$exitButton.BackColor=[Drawing.Color]::FromArgb(16,45,65)})
    $titleBar.Add_Resize({
        $exitButton.Left=[Math]::Max(0,$titleBar.ClientSize.Width-44);$exitButton.Top=3
        $maxButton.Left=[Math]::Max(0,$exitButton.Left-40);$maxButton.Top=3
        $minButton.Left=[Math]::Max(0,$maxButton.Left-40);$minButton.Top=3
        $captionText.Width=[Math]::Max(120,$minButton.Left-48)
    })
    $moveHost={param($sender,$e)
        if($e.Button -ne [System.Windows.Forms.MouseButtons]::Left){return}
        if ($script:workspaceExpanded) { Restore-WorkspaceExpanded -forDrag $true }
        [void][TalepDesktopWindow]::ReleaseCapture()
        [void][TalepDesktopWindow]::SendMessage($window.Handle,0xA1,[IntPtr]2,[IntPtr]0)
    }
    $titleBar.Add_MouseDown($moveHost)
    $captionText.Add_MouseDown($moveHost)
    $captionIcon.Add_MouseDown($moveHost)
    $titleBar.Add_DoubleClick({& $script:toggleSize})
    $captionText.Add_DoubleClick({& $script:toggleSize})

    $window.Add_KeyDown({param($sender,$e)
        # F11 is no longer a forced full-screen shortcut.
        if($e.KeyCode -eq [System.Windows.Forms.Keys]::F11){$e.Handled=$true;$e.SuppressKeyPress=$true}
    })
    $splash=New-Object System.Windows.Forms.Panel
    $splash.Dock=[System.Windows.Forms.DockStyle]::None
    $splash.AutoScroll=$false
    $hostPanel.AutoScroll=$false
    # True transparent cut-out, including unused area around logo and text.
    $splash.BackColor=$script:splashKey
    $hostPanel.Controls.Add($splash)
    # Recalculate at every window state/size change, including edge dragging.
    $window.Add_Resize({Sync-DesktopContentBounds})
    $window.Add_ClientSizeChanged({Sync-DesktopContentBounds})
    $window.Add_Shown({Sync-DesktopContentBounds})
    Sync-DesktopContentBounds

    $brand=New-Object System.Windows.Forms.PictureBox
    $brand.SizeMode='Zoom';$brand.Width=320;$brand.Height=150
    $brand.BackColor=[System.Drawing.Color]::Transparent
    $animatedLogo=Join-Path $Root 'assets\brand\talep-kontrol-acilis.gif'
    if(Test-Path -LiteralPath $animatedLogo -PathType Leaf){$LogoFile=$animatedLogo}
    if(Test-Path -LiteralPath $LogoFile){
        $b=[IO.File]::ReadAllBytes($LogoFile)
        $script:brandStream=New-Object IO.MemoryStream(,$b)
        $brand.Image=[Drawing.Image]::FromStream($script:brandStream)
    }
    $splash.Controls.Add($brand)
    $splashClose=New-Object System.Windows.Forms.Button
    $splashClose.Text='X'
    $splashClose.AccessibleName='Açılış ekranını kapat'
    $splashClose.Size=New-Object Drawing.Size(25,25)
    $splashClose.FlatStyle='Flat'
    $splashClose.BackColor=[Drawing.Color]::Transparent
    $splashClose.ForeColor=[Drawing.Color]::White
    $splashClose.FlatAppearance.BorderSize=0
    $splashClose.FlatAppearance.MouseOverBackColor=[Drawing.Color]::Transparent
    $splashClose.FlatAppearance.MouseDownBackColor=[Drawing.Color]::Transparent
    $splashClose.Add_Click({$window.Close()})
    $brand.Controls.Add($splashClose)
    $splashClose.BringToFront()
    $loading=New-Label 'Talep Kontrol hazırlanıyor' 15 ([Drawing.Color]::White)
    $loading.Font=New-Object System.Drawing.Font('Segoe UI',15,[Drawing.FontStyle]::Bold,[Drawing.GraphicsUnit]::Point)
    $loading.BackColor=[Drawing.Color]::Transparent
    $loading.TextAlign='MiddleCenter';$loading.Height=40;$splash.Controls.Add($loading)
    $detail=New-Label 'Çalışma alanınız hazırlanıyor' 11 ([Drawing.Color]::FromArgb(0,205,234))
    $detail.BackColor=[Drawing.Color]::Transparent
    $detail.TextAlign='MiddleCenter';$detail.Height=58;$splash.Controls.Add($detail)
    # Three slowly breathing dots instead of a fast-moving ellipsis or marquee.
    $dots=@()
    for($i=0;$i -lt 3;$i++){
        $dot=New-Label ([string][char]0x25CF) 13 ([Drawing.Color]::FromArgb(77,142,167))
        $dot.BackColor=[Drawing.Color]::Transparent
        $dot.Width=26;$dot.Height=26;$dot.TextAlign='MiddleCenter'
        $splash.Controls.Add($dot)
        $dots+=,$dot
    }
    # Kept for the error path, hidden during normal loading.
    $progress=New-Object System.Windows.Forms.ProgressBar
    $progress.Style='Blocks';$progress.Width=210;$progress.Height=3;$progress.Visible=$false
    $splash.Controls.Add($progress)
    $openLog=New-Object System.Windows.Forms.Button
    $openLog.Text='Hata günlüğünü aç';$openLog.Width=180;$openLog.Height=36
    $openLog.FlatStyle='Flat';$openLog.BackColor=[Drawing.Color]::FromArgb(235,239,244)
    $openLog.ForeColor=[Drawing.Color]::Black;$openLog.Visible=$false
    $openLog.Add_Click({if(Test-Path -LiteralPath $Log){Start-Process -FilePath 'notepad.exe' -ArgumentList ('"'+$Log+'"')}})
    $splash.Controls.Add($openLog)
    $retry=New-Object System.Windows.Forms.Button
    $retry.Text='Tekrar Dene';$retry.Width=125;$retry.Height=36;$retry.Visible=$false
    $retry.BackColor=[Drawing.Color]::FromArgb(235,239,244);$retry.ForeColor=[Drawing.Color]::Black
    $retry.Add_Click({$window.Close();Start-Process -FilePath 'wscript.exe' -ArgumentList ('"'+(Join-Path $Root 'ACILIS.vbs')+'"') -WindowStyle Hidden})
    $splash.Controls.Add($retry)
    $window.Add_Resize({
        $w=$splash.ClientSize.Width;$h=$splash.ClientSize.Height
        if($w -le 0 -or $h -le 0){return}
        $brand.Width=[Math]::Min(320,[Math]::Max(250,$w-60))
        $brand.Height=150
        $brand.Left=[int](($w-$brand.Width)/2)
        $brand.Top=[Math]::Max(16,[int](($h-380)/2)+20)
        $imageWidth=$brand.Width
        if($brand.Image){$imageWidth=[Math]::Min($brand.Width,[int]($brand.Height*$brand.Image.Width/$brand.Image.Height))}
        $splashClose.Left=[int](($brand.Width+$imageWidth)/2)-$splashClose.Width
        $imageHeight=$brand.Height
        if($brand.Image){$imageHeight=[Math]::Min($brand.Height,[int]($brand.Width*$brand.Image.Height/$brand.Image.Width))}
        $splashClose.Top=[int](($brand.Height-$imageHeight)/2)
        if ($LogoFile -eq $animatedLogo) {
            $splashClose.Left-=8
            $splashClose.Top+=8
        }
        $splashClose.BringToFront()
        $loading.Width=[Math]::Min(475,$w-36)
        $loading.Left=[int](($w-$loading.Width)/2)
        $loading.Top=$brand.Bottom+2
        $loading.Height=32
        $detail.Width=[Math]::Min(480,$w-42)
        $detail.Left=[int](($w-$detail.Width)/2)
        $detail.Top=$loading.Bottom+1
        $detail.Height=51
        for($i=0;$i -lt $dots.Count;$i++){
            $dots[$i].Left=[int](($w-78)/2)+26*$i
            $dots[$i].Top=$detail.Bottom+3
        }
        $progress.Left=[int](($w-$progress.Width)/2)
        $progress.Top=$detail.Bottom+10
        $openLog.Left=[int](($w-315)/2)
        $openLog.Top=$dots[0].Bottom+7
        $retry.Left=$openLog.Right+10
        $retry.Top=$openLog.Top
    })

    # Show the workspace only after the HTML application's initial data boot
    # completes; NavigationCompleted alone means only that HTML was fetched.
    function Show-TalepUpdateResult([string]$result) {
        $json = ConvertTo-Json -InputObject $result -Compress
        [void]$script:web.CoreWebView2.ExecuteScriptAsync("window.dispatchEvent(new CustomEvent('talep-update-result',{detail:$json}));")
    }
    $updateTimer=New-Object System.Windows.Forms.Timer
    $updateTimer.Interval=500
    $updateTimer.Add_Tick({
        if (!$script:updateCheck.Process.HasExited) { return }
        $updateTimer.Stop()
        try {
            $result='kontrol_basarisiz'
            if ($script:updateCheck.Process.ExitCode -eq 0 -and (Test-Path -LiteralPath $script:updateCheck.Status -PathType Leaf)) {
                $result=(Get-Content -LiteralPath $script:updateCheck.Status -Raw -Encoding UTF8 | ConvertFrom-Json).result
            }
            Show-TalepUpdateResult $result
        } catch {
            try { Show-TalepUpdateResult 'kontrol_basarisiz' } catch {}
        } finally {
            $script:updateCheck.Process.Dispose()
            Remove-Item -LiteralPath $script:updateCheck.Status -Force -ErrorAction SilentlyContinue
            $script:updateCheck=$null
        }
    })
    function Open-TalepWorkspace {
        if($script:uiSwapDone -or !$script:navigationReady -or !$script:bootPageReady){return}
        $script:uiSwapDone=$true
        $script:ready=$true
        $timer.Stop()
        try {
            $window.SuspendLayout()
            $window.TransparencyKey=[Drawing.Color]::Empty
            $window.BackColor=[Drawing.Color]::FromArgb(16,45,65)
            $script:workspaceMode=$true
            $splash.Visible=$false
            $screen=[System.Windows.Forms.Screen]::FromControl($window).WorkingArea
            $desiredW=[int][Math]::Min(1600,[Math]::Max(1,$screen.Width*0.92))
            $desiredH=[int][Math]::Min(960,[Math]::Max(1,$screen.Height*0.90))
            $minW=[int][Math]::Min(860,$desiredW)
            $minH=[int][Math]::Min(600,$desiredH)
            $window.MinimumSize=New-Object System.Drawing.Size($minW,$minH)
            $window.WindowState=[System.Windows.Forms.FormWindowState]::Normal
            # A normal-size workspace starts centered; pseudo-maximize uses
            # Screen.WorkingArea when requested via the custom titlebar control.
            $script:workspaceExpanded=$false
            $script:restoreBounds=$null
            $window.MaximizedBounds=$screen
            $window.Size=New-Object System.Drawing.Size($desiredW,$desiredH)
            $window.Location=New-Object System.Drawing.Point(([int]($screen.Left+($screen.Width-$desiredW)/2)),([int]($screen.Top+($screen.Height-$desiredH)/2)))
            $window.EnableEdgeResize=$true
            $window.Text='Talep Kontrol'
            Sync-DesktopContentBounds
            $script:web.BringToFront()
            $titleBar.BringToFront()
            $window.ResumeLayout($true)
            $titleBar.PerformLayout()
            $script:web.PerformLayout()
            $window.Invalidate($true)
            $window.Activate()
            try {
                if ($env:TALEP_UPDATE_RESULT) { Show-TalepUpdateResult $env:TALEP_UPDATE_RESULT }
                if ($BackgroundUpdatePlan) {
                    $process=Start-Process -FilePath $BackgroundUpdatePlan.Python -ArgumentList ($BackgroundUpdatePlan.Args + '--check-only') `
                        -WorkingDirectory $BackgroundUpdatePlan.WorkDir -WindowStyle Hidden -PassThru
                    $script:updateCheck=@{Process=$process; Status=$BackgroundUpdatePlan.Status}
                    $updateTimer.Start()
                }
            } catch {
                Show-TalepUpdateResult 'kontrol_basarisiz'
            }
        } catch {
            $window.ResumeLayout($true)
            Show-Error ('Ana pencere açılamadı: '+$_.Exception.Message)
        }
    }

    $window.Add_Shown({$window.Width=$window.Width+1;$window.Width=$window.Width-1})
    $timer=New-Object System.Windows.Forms.Timer
    $timer.Interval=140
    $timer.Add_Tick({
        if($script:ready){return}
        $script:tickCount++
        # Dot opacity moves gently in a 3-second wave, without moving the text.
        $wave=($script:tickCount*0.14*[Math]::PI*2/3.0)
        for($i=0;$i -lt $dots.Count;$i++){
            $v=0.5+0.5*[Math]::Sin($wave-$i*0.72)
            $v=0.20+0.55*$v
            # Smooth cyan breathing dots on a fully transparent background.
            $r=[int](77+(128-77)*$v)
            $g=[int](142+(211-142)*$v)
            $b=[int](167+(225-167)*$v)
            $dots[$i].ForeColor=[Drawing.Color]::FromArgb($r,$g,$b)
        }
        if($script:tickCount%6 -ne 0){return}
        if(([DateTime]::UtcNow-$script:started).TotalMinutes -gt 5){Show-Error 'Başlatma zaman aşımına uğradı. Ağ, Python ve WebView2 bileşenlerini kontrol edin.';return}
        if($script:svcProc -and $script:svcProc.HasExited -and $script:svcProc.ExitCode -ne 0){
            Show-Error ('Yerel hizmet başlatılamadı (kod '+$script:svcProc.ExitCode+'). Hata günlüğünü inceleyin.');return
        }
        if($script:sdkProc -and $script:sdkProc.HasExited -and $script:sdkProc.ExitCode -ne 0){
            $err='Windows WebView2 bileşenleri hazırlanamadı.'
            if(Test-Path -LiteralPath $SdkState){$err=(Get-Content -LiteralPath $SdkState -Raw).Trim()}
            Show-Error ($err+' Kurumsal ağda gereken paketlere erişim için BT desteği gerekebilir.');return
        }
        if(!$script:sdkPath -and (Test-Path -LiteralPath $SdkState)){
            $line=(Get-Content -LiteralPath $SdkState -Raw -Encoding UTF8).Trim()
            if($line.StartsWith('FAILED|')){Show-Error $line.Substring(7);return}
            if($line.StartsWith('OK|')){$script:sdkPath=$line.Substring(3).Trim()}
        }
        if(!$script:serverPort){
            $s=Get-SessionService
            if($s){
                if($s.error){Show-Error ('Yerel hizmet: '+[string]$s.error);return}
                if($s.port -ge 8765 -and $s.port -le 8769 -and $s.pid -gt 0){
                    $health=Get-Health ([int]$s.port)
                    if($health -and $health.ok -and $health.app -eq 'Talep Kontrol' -and $health.sessionId -eq $script:SessionId -and [int]$health.servicePid -eq [int]$s.pid){
                        $script:serverPort=[int]$s.port;$script:serverPid=[int]$s.pid
                    }
                }
            }
        }
        if(!$script:sdkPath){$detail.Text='Windows uygulama penceresi hazırlanıyor...';return}
        if(!$script:serverPort){$detail.Text='Veri ve raporlama hizmeti başlatılıyor...';return}
        if($script:webStarted){return}
        $script:webStarted=$true
        try{
            $env:PATH=$script:sdkPath+';'+$env:PATH
            Add-Type -Path (Join-Path $script:sdkPath 'Microsoft.Web.WebView2.Core.dll')
            Add-Type -Path (Join-Path $script:sdkPath 'Microsoft.Web.WebView2.WinForms.dll')
            try {
                $browserVersion=[Microsoft.Web.WebView2.Core.CoreWebView2Environment]::GetAvailableBrowserVersionString()
                if([string]::IsNullOrWhiteSpace($browserVersion)){throw 'Runtime bulunamadi.'}
            } catch { throw 'Microsoft Edge WebView2 Runtime bulunamadi veya yuklenemedi. BT tarafindan WebView2 Runtime kurulumu/onarimi gerekiyor.' }
            # Without a custom user data path WebView2 may try writing beside
            # powershell.exe (Program Files / Windows), leading to E_ACCESSDENIED.
            $webUserData=Join-Path $env:LOCALAPPDATA 'TalepKontrol\WebView2UserData'
            New-Item -ItemType Directory -Path $webUserData -Force -ErrorAction Stop | Out-Null
            $probe=Join-Path $webUserData ('write-check-'+$script:SessionId+'.tmp')
            try{[IO.File]::WriteAllText($probe,'ok');Remove-Item -LiteralPath $probe -Force}
            catch{throw ('WebView2 kullanıcı veri klasörüne yazılamıyor: '+$webUserData+' ('+$_.Exception.Message+')')}
            $script:web=New-Object Microsoft.Web.WebView2.WinForms.WebView2
            $creation=New-Object Microsoft.Web.WebView2.WinForms.CoreWebView2CreationProperties
            $creation.UserDataFolder=$webUserData
            $script:web.CreationProperties=$creation
            $script:web.Dock=[System.Windows.Forms.DockStyle]::None
            $hostPanel.Controls.Add($script:web)
            # Offscreen until the page has finished INITIAL data initialization.
            $script:web.BringToFront();$splash.BringToFront()
            Sync-DesktopContentBounds
            $script:web.Add_CoreWebView2InitializationCompleted({param($sender,$e)
                if(!$e.IsSuccess){
                    $why='Bilinmeyen hata'
                    if($e.InitializationException){$why=$e.InitializationException.Message}
                    Show-Error ('WebView2 başlatılamadı: '+$why+'. Kullanıcı veri klasörü: '+(Join-Path $env:LOCALAPPDATA 'TalepKontrol\WebView2UserData')+'. Sorun sürerse kurumsal BT ile WebView2 çalışma izinlerini kontrol edin.')
                    return
                }
                try {$sender.CoreWebView2.Settings.AreDefaultContextMenusEnabled=$false} catch{}
                # The localhost page reports when navigation is usable. Source loading continues separately.
                try {
                    $sender.CoreWebView2.Add_WebMessageReceived({param($core,$msg)
                        try {
                            $expected='http://127.0.0.1:'+$script:serverPort+'/'
                            if(!$msg.Source.StartsWith($expected,[System.StringComparison]::OrdinalIgnoreCase)){return}
                            $data=([string]$msg.WebMessageAsJson | ConvertFrom-Json)
                            if($data.type -eq 'talep-ui-ready'){
                                $script:bootPageReady=$true
                                Open-TalepWorkspace
                            } elseif($data.type -eq 'talep-ui-boot-error') {
                                Show-Error ('Veri hazırlama tamamlanamadı: '+[string]$data.message)
                            }
                        }catch{
                            try { Add-Content -LiteralPath $Log -Value ((Get-Date -Format s)+' | GUI | UI message: '+$_.Exception.Message) -Encoding UTF8 } catch {}
                        }
                    })
                } catch { Show-Error ('WebView2 olay bağlantısı kurulamadı: '+$_.Exception.Message) }
            })
            $script:web.Add_NavigationCompleted({param($sender,$e)
                if($e.IsSuccess){
                    $script:navigationReady=$true
                    Open-TalepWorkspace
                } else {
                    Show-Error ('Uygulama ekranı yüklenemedi: '+$e.WebErrorStatus)
                }
            })
            $script:web.Source=[Uri]('http://127.0.0.1:'+$script:serverPort+'/')
            $detail.Text='Talep Kontrol çalışma alanı açılıyor...'
        }catch{Show-Error ('Uygulama penceresi açılamadı: '+$_.Exception.Message)}
    })
    $window.Add_Shown({
        try{
            $env:TALEP_LAUNCHER_NO_BROWSER='1'
            $env:TALEP_GUI_SESSION=$script:SessionId
            $env:TALEP_GUI_SHUTDOWN_TOKEN=$script:SessionToken
            $env:TALEP_GUI_STATUS=$script:SessionState
            $pythonBootstrap=Join-Path $Root 'PYTHON_BOOTSTRAP.ps1'
            $sdkPrepare=Join-Path $Root 'WEBVIEW2_HAZIRLA.ps1'
            if(!(Test-Path $pythonBootstrap) -or !(Test-Path $sdkPrepare)){throw 'Kurulum dosyaları eksik.'}
            $psExe=Join-Path $PSHOME 'powershell.exe'
            $script:svcProc=Start-Process -FilePath $psExe -ArgumentList ('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "'+$pythonBootstrap+'"') -WorkingDirectory $Root -WindowStyle Hidden -PassThru
            $script:sdkProc=Start-Process -FilePath $psExe -ArgumentList ('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "'+$sdkPrepare+'" -State "'+$SdkState+'"') -WorkingDirectory $Root -WindowStyle Hidden -PassThru
            $script:started=[DateTime]::UtcNow;$timer.Start()
        }catch{Show-Error ('Başlatma bileşeni çalıştırılamadı: '+$_.Exception.Message)}
    })
    $window.Add_FormClosing({Stop-LocalService})
    $window.Add_FormClosed({
        $updateTimer.Stop()
        $updateTimer.Dispose()
        if ($script:updateCheck) {
            # The check may finish writing its durable marker after close.
            $script:updateCheck.Process.Dispose()
        }
        try{if($script:web){$script:web.Dispose()}}catch{}
        try{if($brand.Image){$brand.Image.Dispose()}}catch{}
        try{if($script:brandStream){$script:brandStream.Dispose()}}catch{}
        try{if($window.Icon){$window.Icon.Dispose()}}catch{}
    })
    [System.Windows.Forms.Application]::Run($window)
} catch {
    Stop-LocalService
    [System.Windows.Forms.MessageBox]::Show(('Talep Kontrol açılamadı: '+$_.Exception.Message),'Talep Kontrol',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Error)|Out-Null
    exit 91
}
