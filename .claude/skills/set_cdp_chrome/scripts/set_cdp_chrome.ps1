#Requires -Version 5.1
<#
 set_cdp_chrome.ps1 - Dedicated Chrome shortcut for a CDP (Chrome DevTools Protocol) channel.

 A "channel" is a port + a dedicated profile. This script creates a Windows shortcut (.lnk) that starts
 Chrome with --remote-debugging-port=<port> and its own --user-data-dir, with a badged Chrome icon so it
 is visually distinct from the normal Chrome icon. Chrome 136+ ignores --remote-debugging-port on the
 default profile, so the dedicated profile is mandatory, not optional.

 Actions (positional):
   add    [port]   create badged icon + shortcut (Desktop; -StartMenu adds Start Menu entry; -NoDesktop skips Desktop)
   list            list CDP shortcuts (channels) on Desktop / Start Menu and whether each port answers
   status [port]   liveness check: http://127.0.0.1:<port>/json/version
   launch [port]   start Chrome with the same arguments as the shortcut, wait until CDP answers
   stop   [port]   terminate the Chrome browser process that owns that debugging port
   remove [port]   delete shortcut(s) + icon; -Purge also deletes the profile directory
   path            print the chrome.exe path that would be used
   help            usage text (the only action that does not print JSON)

 Output: exactly ONE JSON object on stdout ({"ok": bool, "action": ..., ...}); "warnings"/"hint" fields carry
 non-fatal notes. Exit codes: 0 ok, 1 error, 2 not found / conflict / refused.
 All text in this file is ASCII on purpose (PowerShell 5.1 reads BOM-less files as ANSI).
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('add', 'list', 'status', 'launch', 'stop', 'remove', 'path', 'help')]
    [string]$Action = 'help',

    [Parameter(Position = 1)]
    [int]$Port = 0,

    [string]$Name,                      # shortcut display name (default: "Chrome CDP (<port>)")
    [string]$Label = 'CDP',             # text drawn on the icon badge
    [string]$Color = '#7C3AED',         # badge color (HTML hex)
    [string]$ProfileDir,                # custom --user-data-dir (default: %LOCALAPPDATA%\ChromeCDP\profiles\<port>)
    [string]$ChromePath,                # override chrome.exe location
    [string[]]$ExtraArgs = @(),         # extra chrome flags appended to the shortcut
    [switch]$StartMenu,                 # also create a Start Menu shortcut
    [switch]$NoDesktop,                 # do not create the Desktop shortcut
    [switch]$Launch,                    # after add: launch and verify
    [switch]$Headless,                  # launch: add --headless=new (no window; for tests/CI)
    [switch]$AllowOrigins,              # add --remote-allow-origins=* (needed by browser-based CDP clients; security trade-off)
    [switch]$Force,                     # add: overwrite existing shortcut; remove: also remove unmanaged shortcuts / outside profiles
    [switch]$Purge,                     # remove: delete the profile directory too
    [switch]$DryRun,                    # add / remove: report the plan, touch nothing
    [int]$TimeoutSec = 20               # launch: how long to wait for the endpoint
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

# ---------------------------------------------------------------- constants / state
$DefaultPort  = 9222
$Tag          = 'set_cdp_chrome'
$Root         = Join-Path $env:LOCALAPPDATA 'ChromeCDP'
$IconDir      = Join-Path $Root 'icons'
$ProfileRoot  = Join-Path $Root 'profiles'
$DesktopDir   = [Environment]::GetFolderPath('Desktop')
$ProgramsDir  = [Environment]::GetFolderPath('Programs')
$IconSizes    = @(256, 64, 48, 32, 16)
$script:ExitCode = 0
$script:Warnings = New-Object System.Collections.Generic.List[string]

# ---------------------------------------------------------------- native helpers
Add-Type -AssemblyName System.Drawing
if (-not ([System.Management.Automation.PSTypeName]'ChromeCdpNative').Type) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ChromeCdpNative {
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int PrivateExtractIcons(string lpszFile, int nIconIndex, int cxIcon, int cyIcon,
        IntPtr[] phicon, int[] piconid, int nIcons, int flags);
    [DllImport("user32.dll")]
    public static extern bool DestroyIcon(IntPtr hIcon);
    [DllImport("shell32.dll")]
    public static extern void SHChangeNotify(int wEventId, int uFlags, IntPtr dwItem1, IntPtr dwItem2);
}
'@
}

# ---------------------------------------------------------------- JSON output helpers
function Warn([string]$s) { $script:Warnings.Add($s) }

function Emit($obj, [int]$code) {
    # The one and only stdout write. Everything else in this script must stay silent.
    if ($script:Warnings.Count -gt 0 -and -not $obj.Contains('warnings')) { $obj['warnings'] = @($script:Warnings) }
    Write-Output ($obj | ConvertTo-Json -Depth 8)
    exit $code
}

function Fail([string]$action, [string]$err, [string]$hint, [int]$code, $extra) {
    $o = [ordered]@{ ok = $false; action = $action; error = $err }
    if ($hint) { $o.hint = $hint }
    if ($extra) { foreach ($k in $extra.Keys) { $o[$k] = $extra[$k] } }
    Emit $o $code
}

function Show-Help {
    @"
set_cdp_chrome.ps1 <action> [port] [options]     (stdout: one JSON object, except help)

actions
  add    [port]   create badged icon + shortcut (default port $DefaultPort)
  list            list CDP shortcuts (channels) + endpoint state
  status [port]   liveness: http://127.0.0.1:<port>/json/version
  launch [port]   start Chrome like the shortcut does and wait for CDP
  stop   [port]   terminate the Chrome that owns that debugging port
  remove [port]   delete shortcut(s) + icon (-Purge: profile dir too)
  path            print chrome.exe path

options
  -Name <text>        shortcut name            -Label <text>     badge text (default CDP)
  -Color <#hex>       badge color              -ProfileDir <dir> custom user-data-dir
  -ChromePath <exe>   chrome.exe override      -ExtraArgs a,b    extra chrome flags
  -StartMenu          also Start Menu entry    -NoDesktop        skip Desktop shortcut
  -Launch             launch after add         -Headless         launch without a window
  -AllowOrigins       add --remote-allow-origins=*   -Force        overwrite / include unmanaged
  -Purge              remove profile dir too   -DryRun           add/remove: plan only
  -TimeoutSec <n>     launch wait (default 20)

exit codes: 0 ok, 1 error, 2 not found / conflict / refused
"@ | Write-Output
}

# ---------------------------------------------------------------- discovery
function Find-Chrome {
    if ($ChromePath) {
        if (Test-Path -LiteralPath $ChromePath) { return (Resolve-Path -LiteralPath $ChromePath).Path }
        throw "ChromePath not found: $ChromePath"
    }
    $candidates = New-Object System.Collections.Generic.List[string]
    foreach ($k in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
                     'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe')) {
        try {
            $v = (Get-ItemProperty -Path $k -ErrorAction Stop).'(default)'
            if ($v) { $candidates.Add($v) }
        } catch { }
    }
    $candidates.Add((Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'))
    if (${env:ProgramFiles(x86)}) { $candidates.Add((Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe')) }
    $candidates.Add((Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'))
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

function Resolve-Port([int]$p) {
    if ($p -gt 0) { return $p }
    # no port given: if exactly one managed shortcut exists use its port, else the default
    $managed = @(Get-CdpShortcuts | Where-Object { $_.Managed })
    if ($managed.Count -eq 1) { return [int]$managed[0].Port }
    return $DefaultPort
}

function Get-SafeName([string]$s) {
    $invalid = [IO.Path]::GetInvalidFileNameChars() -join ''
    $re = '[{0}]' -f [regex]::Escape($invalid)
    return ($s -replace $re, '_').Trim()
}

function Get-ChromeArgs([int]$port, [string]$profile, [bool]$allowOrigins, [bool]$headless, [string[]]$extra) {
    $list = New-Object System.Collections.Generic.List[string]
    $list.Add("--remote-debugging-port=$port")
    $list.Add('--remote-debugging-address=127.0.0.1')
    $list.Add('--user-data-dir="' + $profile + '"')
    $list.Add('--no-first-run')
    $list.Add('--no-default-browser-check')
    if ($allowOrigins) { $list.Add('--remote-allow-origins=*') }
    if ($headless)     { $list.Add('--headless=new') }
    foreach ($e in $extra) { if ($e) { $list.Add($e) } }
    return ($list -join ' ')
}

# ---------------------------------------------------------------- shortcut helpers
function Get-CdpShortcuts {
    # Every .lnk on Desktop / Start Menu that targets chrome.exe with --remote-debugging-port.
    # Managed = created by this script (Description carries the tag).
    $ws = New-Object -ComObject WScript.Shell
    $dirs = @($DesktopDir, $ProgramsDir) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    foreach ($d in $dirs) {
        foreach ($f in (Get-ChildItem -LiteralPath $d -Filter *.lnk -File -ErrorAction SilentlyContinue)) {
            try { $s = $ws.CreateShortcut($f.FullName) } catch { continue }
            $args = [string]$s.Arguments
            if ($args -notmatch '--remote-debugging-port=(\d+)') { continue }
            $port = [int]$Matches[1]
            $profile = ''
            if ($args -match '--user-data-dir="([^"]+)"') { $profile = $Matches[1] }
            elseif ($args -match '--user-data-dir=(\S+)') { $profile = $Matches[1] }
            [pscustomobject]@{
                Path      = $f.FullName
                Location  = $(if ($d -eq $DesktopDir) { 'Desktop' } else { 'StartMenu' })
                Port      = $port
                Profile   = $profile
                Target    = [string]$s.TargetPath
                Arguments = $args
                Icon      = [string]$s.IconLocation
                Managed   = ([string]$s.Description) -like "$Tag;*"
            }
        }
    }
}

function New-Lnk([string]$path, [string]$target, [string]$arguments, [string]$icon, [string]$desc) {
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($path)
    $s.TargetPath       = $target
    $s.Arguments        = $arguments
    $s.WorkingDirectory = (Split-Path -Parent $target)
    $s.IconLocation     = "$icon,0"
    $s.Description      = $desc
    $s.WindowStyle      = 1
    $s.Save()
}

function Refresh-IconCache {
    # SHCNE_ASSOCCHANGED (0x08000000), SHCNF_FLUSH (0x1000): asks Explorer to re-read icons.
    try { [ChromeCdpNative]::SHChangeNotify(0x08000000, 0x1000, [IntPtr]::Zero, [IntPtr]::Zero) } catch { }
}

# ---------------------------------------------------------------- icon rendering
function Get-ExeIconBitmap([string]$exe, [int]$size) {
    $h = New-Object IntPtr[] 1
    $ids = New-Object int[] 1
    $n = [ChromeCdpNative]::PrivateExtractIcons($exe, 0, $size, $size, $h, $ids, 1, 0)
    if ($n -lt 1 -or $h[0] -eq [IntPtr]::Zero) { return $null }
    try {
        $ico = [System.Drawing.Icon]::FromHandle($h[0])
        return $ico.ToBitmap()
    } finally {
        [ChromeCdpNative]::DestroyIcon($h[0]) | Out-Null
    }
}

function New-RoundedRectPath([System.Drawing.RectangleF]$r, [single]$rad) {
    $p = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $rad * 2
    $p.AddArc($r.X, $r.Y, $d, $d, 180, 90)
    $p.AddArc($r.Right - $d, $r.Y, $d, $d, 270, 90)
    $p.AddArc($r.Right - $d, $r.Bottom - $d, $d, $d, 0, 90)
    $p.AddArc($r.X, $r.Bottom - $d, $d, $d, 90, 90)
    $p.CloseFigure()
    return $p
}

function New-BadgedBitmap([System.Drawing.Bitmap]$base, [int]$size, [string]$label, [System.Drawing.Color]$color) {
    $bmp = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    try {
        $g.SmoothingMode     = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.PixelOffsetMode   = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
        $g.Clear([System.Drawing.Color]::Transparent)
        $g.DrawImage($base, 0, 0, $size, $size)

        # badge: rounded banner across the bottom ~38% of the icon
        $bh  = [single]($size * 0.38)
        $pad = [single][Math]::Max(0.5, $size * 0.03)
        $rect = New-Object System.Drawing.RectangleF($pad, ($size - $bh), ($size - 2 * $pad), ($bh - $pad))
        $radius = [single][Math]::Max(1.5, $size * 0.09)
        $path = New-RoundedRectPath $rect $radius

        # soft shadow under the badge so it separates from the logo
        if ($size -ge 32) {
            $shadowRect = New-Object System.Drawing.RectangleF($rect.X, ($rect.Y + $size * 0.012), $rect.Width, $rect.Height)
            $shadowPath = New-RoundedRectPath $shadowRect $radius
            $shadow = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(90, 0, 0, 0))
            $g.FillPath($shadow, $shadowPath)
            $shadow.Dispose(); $shadowPath.Dispose()
        }

        $brush = New-Object System.Drawing.SolidBrush($color)
        $g.FillPath($brush, $path)
        $brush.Dispose()

        if ($size -ge 32) {
            $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(235, 255, 255, 255), [single][Math]::Max(1, $size * 0.012))
            $g.DrawPath($pen, $path)
            $pen.Dispose()
        }

        if ($size -ge 48 -and $label) {
            $fontPx = [single]($bh * 0.60)
            $font = New-Object System.Drawing.Font('Segoe UI', $fontPx, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
            while (($g.MeasureString($label, $font).Width -gt ($rect.Width * 0.90)) -and $fontPx -gt 5) {
                $fontPx -= 1
                $font.Dispose()
                $font = New-Object System.Drawing.Font('Segoe UI', $fontPx, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
            }
            $sf = New-Object System.Drawing.StringFormat
            $sf.Alignment     = [System.Drawing.StringAlignment]::Center
            $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
            $textRect = New-Object System.Drawing.RectangleF($rect.X, ($rect.Y - $size * 0.005), $rect.Width, $rect.Height)
            $g.DrawString($label, $font, [System.Drawing.Brushes]::White, $textRect, $sf)
            $sf.Dispose(); $font.Dispose()
        }
        $path.Dispose()
    } finally {
        $g.Dispose()
    }
    return $bmp
}

function Write-Ico([System.Collections.Generic.List[System.Drawing.Bitmap]]$images, [string]$path) {
    # ICO container with PNG-compressed frames (supported since Windows Vista).
    $pngs = New-Object 'System.Collections.Generic.List[byte[]]'
    foreach ($img in $images) {
        $ms = New-Object IO.MemoryStream
        $img.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $pngs.Add($ms.ToArray())
        $ms.Dispose()
    }
    $count = $images.Count
    $fs = [IO.File]::Create($path)
    $bw = New-Object IO.BinaryWriter($fs)
    try {
        $bw.Write([uint16]0); $bw.Write([uint16]1); $bw.Write([uint16]$count)
        $offset = 6 + 16 * $count
        for ($i = 0; $i -lt $count; $i++) {
            $w = $images[$i].Width; $h = $images[$i].Height
            $bw.Write([byte]$(if ($w -ge 256) { 0 } else { $w }))
            $bw.Write([byte]$(if ($h -ge 256) { 0 } else { $h }))
            $bw.Write([byte]0)          # color count
            $bw.Write([byte]0)          # reserved
            $bw.Write([uint16]1)        # planes
            $bw.Write([uint16]32)       # bpp
            $bw.Write([uint32]$pngs[$i].Length)
            $bw.Write([uint32]$offset)
            $offset += $pngs[$i].Length
        }
        foreach ($p in $pngs) { $bw.Write($p) }
        $bw.Flush()
    } finally {
        $bw.Dispose(); $fs.Dispose()
    }
}

function New-CdpIcon([string]$chrome, [string]$icoPath, [string]$label, [string]$colorHex) {
    $color = [System.Drawing.ColorTranslator]::FromHtml($colorHex)
    $frames = New-Object 'System.Collections.Generic.List[System.Drawing.Bitmap]'
    $fallback = $null
    foreach ($sz in $IconSizes) {
        $base = Get-ExeIconBitmap $chrome $sz
        if (-not $base) {
            if (-not $fallback) { $fallback = [System.Drawing.Icon]::ExtractAssociatedIcon($chrome).ToBitmap() }
            $base = $fallback
        }
        $frames.Add((New-BadgedBitmap $base $sz $label $color))
        if ($base -ne $fallback) { $base.Dispose() }
    }
    Write-Ico $frames $icoPath
    # 256px PNG preview next to the .ico so the result can be inspected without Explorer
    $preview = [IO.Path]::ChangeExtension($icoPath, '.png')
    $frames[0].Save($preview, [System.Drawing.Imaging.ImageFormat]::Png)
    foreach ($f in $frames) { $f.Dispose() }
    if ($fallback) { $fallback.Dispose() }
    return $preview
}

# ---------------------------------------------------------------- endpoint / process helpers
function Get-CdpVersion([int]$port) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/json/version" -UseBasicParsing -TimeoutSec 3
        return ($r.Content | ConvertFrom-Json)
    } catch { return $null }
}

function Get-CdpTargets([int]$port) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/json/list" -UseBasicParsing -TimeoutSec 3
        return @($r.Content | ConvertFrom-Json)
    } catch { return @() }
}

function Get-NetstatListeners([int]$port) {
    # Fallback for environments where the CIM-backed cmdlets are unavailable (Windows Sandbox answers
    # "Access is denied" for WMI even when elevated). Rows are shaped like Get-NetTCPConnection output.
    $re = '^\s*TCP\s+(\S+):' + $port + '\s+(\S+)\s+(\S+)\s+(\d+)\s*$'
    @(netstat -ano -p TCP 2>$null | ForEach-Object {
        if (($_ -match $re) -and (($Matches[3] -like 'LISTEN*') -or ($Matches[2] -match ':0$'))) {
            [pscustomobject]@{ LocalAddress = $Matches[1]; LocalPort = $port; OwningProcess = [int]$Matches[4] }
        }
    })
}

function Get-PortListener([int]$port) {
    try {
        return @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop)
    } catch { return @(Get-NetstatListeners $port) }
}

function Get-SocketOwnerProcesses([int]$port) {
    # chrome.exe processes that own the LISTENING socket on <port>, shaped like Win32_Process rows.
    # The listening socket always belongs to the browser process, never to a --type= child.
    @(Get-NetstatListeners $port | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        $p = Get-Process -Id $_ -ErrorAction SilentlyContinue
        if ($p -and $p.Name -eq 'chrome') { [pscustomobject]@{ ProcessId = [int]$_; Name = 'chrome.exe'; CommandLine = $null } }
    })
}

function Get-CdpProcesses([int]$port) {
    # Child processes (renderer/gpu/utility) inherit the flag but always carry --type=...; only the
    # browser process lacks it. Killing the browser process is enough: children exit on their own.
    # WMI is the primary source (the command line is authoritative). Only when WMI itself is unavailable
    # do we fall back to the owner of the listening socket.
    $re = "--remote-debugging-port=$port(\s|$)"
    try {
        return @(Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -and ($_.CommandLine -match $re) -and ($_.CommandLine -notmatch '\s--type=') })
    } catch {
        if (-not $script:WmiWarned) {
            $script:WmiWarned = $true
            Warn ('WMI process lookup unavailable (' + $_.Exception.Message.Trim() + '); using the owner of the listening socket instead.')
        }
        return @(Get-SocketOwnerProcesses $port)
    }
}

function Merge-Endpoint($R, [int]$port, $ver) {
    $R.endpoint = "http://127.0.0.1:$port"
    $R.browser  = [string]$ver.Browser
    $R.protocol = [string]$ver.'Protocol-Version'
    $R.ws       = [string]$ver.webSocketDebuggerUrl
    $R.targets  = @(foreach ($t in (Get-CdpTargets $port)) {
        [ordered]@{ type = [string]$t.type; id = [string]$t.id; url = [string]$t.url; title = [string]$t.title }
    })
}

# ---------------------------------------------------------------- actions
function Invoke-Path {
    $c = Find-Chrome
    if ($c) { Emit ([ordered]@{ ok = $true; action = 'path'; chrome = $c }) 0 }
    Fail 'path' 'chrome.exe not found (App Paths registry, Program Files, LOCALAPPDATA).' 'Pass -ChromePath <full path to chrome.exe>.' 2 $null
}

function Invoke-List {
    $items = @(Get-CdpShortcuts)
    $channels = @(foreach ($it in $items) {
        $ver = Get-CdpVersion $it.Port
        $state = 'stopped'
        if ($ver) { $state = 'listening' }
        elseif ((Get-PortListener $it.Port).Count -gt 0) { $state = 'port-in-use-by-other' }
        $o = [ordered]@{
            port = $it.Port; state = $state; managed = [bool]$it.Managed; location = $it.Location
            shortcut = $it.Path; profile = $it.Profile; target = $it.Target; args = $it.Arguments
        }
        if ($ver) { $o.browser = [string]$ver.Browser; $o.ws = [string]$ver.webSocketDebuggerUrl }
        $o
    })
    $R = [ordered]@{ ok = $true; action = 'list'; count = $items.Count; channels = $channels }
    if ($items.Count -eq 0) { $R.hint = 'No CDP shortcuts on Desktop or Start Menu. Create one with: add [port]' }
    Emit $R 0
}

function Invoke-Status([int]$port) {
    $ver = Get-CdpVersion $port
    if ($ver) {
        $R = [ordered]@{ ok = $true; action = 'status'; port = $port; state = 'listening' }
        Merge-Endpoint $R $port $ver
        Emit $R 0
    }
    $listeners = Get-PortListener $port
    if ($listeners.Count -gt 0) {
        $pids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
        Fail 'status' "Port $port is in use by a process that does not answer /json/version." `
            'Pick another port (port_manager suggest) or stop that process.' 2 `
            ([ordered]@{ port = $port; state = 'port-in-use-by-other'; pids = $pids })
    }
    $sc = @(Get-CdpShortcuts | Where-Object { $_.Port -eq $port })
    $hint = 'Double-click the shortcut or run: launch ' + $port
    if ($sc.Count -eq 0) { $hint = 'No shortcut for this port yet. Create with: add ' + $port }
    Emit ([ordered]@{ ok = $false; action = 'status'; port = $port; state = 'stopped'; shortcuts = $sc.Count; hint = $hint }) 2
}

function Invoke-Launch([int]$port, [bool]$fromAdd) {
    # Returns an ordered hashtable and sets $script:ExitCode; never writes to the pipeline itself,
    # so `add -Launch` can embed the result in its own JSON.
    $R = [ordered]@{ ok = $false; action = 'launch'; port = $port; state = 'unknown' }
    $existing = Get-CdpVersion $port
    if ($existing) {
        $R.ok = $true; $R.state = 'already-listening'
        Merge-Endpoint $R $port $existing
        $script:ExitCode = 0
        return $R
    }
    if ((Get-PortListener $port).Count -gt 0) {
        $R.state = 'port-in-use-by-other'
        $R.error = "Port $port is in use by a non-CDP process."
        $R.hint = 'Choose another port.'
        $script:ExitCode = 2
        return $R
    }
    $chrome = Find-Chrome
    if (-not $chrome) {
        $R.error = 'chrome.exe not found.'; $R.hint = 'Pass -ChromePath.'
        $script:ExitCode = 2
        return $R
    }

    # Prefer the arguments recorded in the managed shortcut so launch == double-click.
    $sc = @(Get-CdpShortcuts | Where-Object { $_.Port -eq $port -and $_.Managed })
    if ($sc.Count -gt 0 -and -not $fromAdd) {
        $argString = $sc[0].Arguments
        if ($Headless -and $argString -notmatch '--headless') { $argString += ' --headless=new' }
        $chrome = $sc[0].Target
        $R.source = 'shortcut'; $R.shortcut = $sc[0].Path
    } else {
        $profile = $ProfileDir
        if (-not $profile) { $profile = Join-Path $ProfileRoot "$port" }
        New-Item -ItemType Directory -Force -Path $profile | Out-Null
        $argString = Get-ChromeArgs $port $profile $AllowOrigins.IsPresent $Headless.IsPresent $ExtraArgs
        $R.source = 'defaults'
    }
    $R.chrome = $chrome
    $R.args = $argString
    $p = Start-Process -FilePath $chrome -ArgumentList $argString -PassThru
    $R.pid = [int]$p.Id

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $ver = $null
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 400
        $ver = Get-CdpVersion $port
        if ($ver) { break }
    }
    if ($ver) {
        $R.ok = $true; $R.state = 'listening'
        Merge-Endpoint $R $port $ver
        $script:ExitCode = 0
        return $R
    }
    $R.state = 'not-answering'
    $R.error = "Chrome started but CDP did not answer on $port within ${TimeoutSec}s."
    $R.hint = 'Usually another Chrome already runs with the same --user-data-dir (it only opened a new window). Run: stop <port>, then launch again.'
    $script:ExitCode = 1
    return $R
}

function Invoke-Stop([int]$port) {
    # @() matters: a single CimInstance has no usable .Count in PowerShell 5.1
    $procs = @(Get-CdpProcesses $port)
    $R = [ordered]@{ ok = $true; action = 'stop'; port = $port; state = 'stopped'; killed = @() }
    if ($procs.Count -eq 0) {
        # Never report "stopped" on the strength of an empty process list alone: the endpoint decides.
        if (-not (Get-CdpVersion $port)) {
            $R.hint = "No chrome.exe with --remote-debugging-port=$port is running."
            Emit $R 0
        }
        $procs = @(Get-SocketOwnerProcesses $port)
        if ($procs.Count -eq 0) {
            $R.ok = $false; $R.state = 'still-listening'
            $R.error = "Port $port answers /json/version but no owning chrome.exe could be identified."
            $R.hint = "Close the Chrome window that uses this profile by hand, then run: status $port"
            Emit $R 1
        }
        Warn ("Process lookup by command line found nothing although port $port answers; stopping the socket owner instead (PID " + (($procs | ForEach-Object { $_.ProcessId }) -join ', ') + ').')
    }
    $killed = New-Object System.Collections.Generic.List[int]
    foreach ($p in $procs) {
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; $killed.Add([int]$p.ProcessId) }
        catch { Warn "Could not stop PID $($p.ProcessId): $($_.Exception.Message)" }
    }
    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $deadline -and (Get-CdpVersion $port)) { Start-Sleep -Milliseconds 300 }
    $R.killed = @($killed)
    if (Get-CdpVersion $port) {
        $R.ok = $false; $R.state = 'still-listening'
        $R.error = "Port $port still answers after Stop-Process."
        Emit $R 1
    }
    Emit $R 0
}

function Invoke-Add([int]$port) {
    $chrome = Find-Chrome
    if (-not $chrome) { Fail 'add' 'chrome.exe not found (App Paths registry, Program Files, LOCALAPPDATA).' 'Pass -ChromePath <full path to chrome.exe>.' 2 $null }
    if ($NoDesktop -and -not $StartMenu) { Fail 'add' '-NoDesktop without -StartMenu would create nothing.' 'Drop -NoDesktop or add -StartMenu.' 2 $null }

    $profile = $ProfileDir
    if (-not $profile) { $profile = Join-Path $ProfileRoot "$port" }
    $profile = [IO.Path]::GetFullPath($profile)

    $displayName = $Name
    if (-not $displayName) { $displayName = "Chrome CDP ($port)" }
    $displayName = Get-SafeName $displayName

    $targets = New-Object System.Collections.Generic.List[string]
    if (-not $NoDesktop) { $targets.Add((Join-Path $DesktopDir "$displayName.lnk")) }
    if ($StartMenu)      { $targets.Add((Join-Path $ProgramsDir "$displayName.lnk")) }

    # one port = one channel: refuse a second shortcut for the same port under another name unless -Force
    $same = @(Get-CdpShortcuts | Where-Object { $_.Port -eq $port })
    $clash = @($same | Where-Object { $targets -notcontains $_.Path })
    if ($clash.Count -gt 0 -and -not $Force) {
        $existing = @(foreach ($c in $clash) { [ordered]@{ shortcut = $c.Path; profile = $c.Profile; managed = [bool]$c.Managed } })
        Fail 'add' "A shortcut for port $port already exists under another name." `
            "Run: remove $port first, or add -Force to create another one anyway." 2 `
            ([ordered]@{ port = $port; state = 'conflict'; existing = $existing })
    }
    foreach ($t in $targets) {
        if ((Test-Path -LiteralPath $t) -and -not $Force) {
            Fail 'add' "Shortcut already exists: $t" 'Add -Force to overwrite it.' 2 ([ordered]@{ port = $port; state = 'exists'; shortcut = $t })
        }
    }

    # port sanity: warn (not fail) if something else already listens there
    if (-not (Get-CdpVersion $port) -and (Get-PortListener $port).Count -gt 0) {
        Warn "Port $port is currently in use by another process; Chrome will fail to bind it while that process runs."
    }
    if ($AllowOrigins) { Warn '--remote-allow-origins=* lets any web page that knows the port attach to this browser. Use only with a throwaway profile.' }

    $ico = Join-Path $IconDir "chrome-cdp-$port.ico"
    $preview = [IO.Path]::ChangeExtension($ico, '.png')
    $argString = Get-ChromeArgs $port $profile $AllowOrigins.IsPresent $false $ExtraArgs
    $R = [ordered]@{
        ok = $true; action = 'add'; dry_run = $DryRun.IsPresent
        chrome = $chrome; port = $port; name = $displayName; profile = $profile
        icon = $ico; preview = $preview; shortcuts = @($targets); args = $argString
        endpoint = "http://127.0.0.1:$port/json/version"
        notes = @(
            'Taskbar pin cannot be scripted on Windows 10/11: right-click the shortcut > Pin to taskbar.',
            'Dedicated profile: sign in again inside this Chrome; personal bookmarks and cookies are not shared.'
        )
    }
    if ($DryRun) { Emit $R 0 }

    New-Item -ItemType Directory -Force -Path $IconDir, $profile | Out-Null
    $null = New-CdpIcon $chrome $ico $Label $Color
    foreach ($t in $targets) { New-Lnk $t $chrome $argString $ico "$Tag;port=$port" }
    Refresh-IconCache

    if ($Launch) {
        $R.launch = @(Invoke-Launch $port $true)[-1]
        if ($script:ExitCode -ne 0) { $R.ok = $false }
        Emit $R $script:ExitCode
    }
    Emit $R 0
}

function Invoke-Remove([int]$port) {
    $all = @(Get-CdpShortcuts | Where-Object { $_.Port -eq $port })
    $unmanaged = @($all | Where-Object { -not $_.Managed })
    $items = $all
    if (-not $Force) { $items = @($all | Where-Object { $_.Managed }) }
    $running = @(Get-CdpProcesses $port)

    $ico = Join-Path $IconDir "chrome-cdp-$port.ico"
    $icons = @(@($ico, [IO.Path]::ChangeExtension($ico, '.png')) | Where-Object { Test-Path -LiteralPath $_ })

    $profiles = New-Object System.Collections.Generic.List[string]
    foreach ($it in $items) { if ($it.Profile -and -not $profiles.Contains($it.Profile)) { $profiles.Add($it.Profile) } }
    if ($profiles.Count -eq 0) { $profiles.Add((Join-Path $ProfileRoot "$port")) }
    $existingProfiles = @($profiles | Where-Object { Test-Path -LiteralPath $_ })

    $R = [ordered]@{
        ok = $true; action = 'remove'; dry_run = $DryRun.IsPresent; port = $port; chrome_running = ($running.Count -gt 0)
        removed_shortcuts = @(); removed_icons = @(); removed_profiles = @(); kept_profiles = @()
    }
    if ($DryRun) {
        $R.would_remove_shortcuts = @($items | ForEach-Object { $_.Path })
        $R.would_remove_icons = $icons
        if ($Purge -and $running.Count -eq 0) { $R.would_remove_profiles = $existingProfiles } else { $R.kept_profiles = $existingProfiles }
        if ($unmanaged.Count -gt 0 -and -not $Force) { $R.hint = 'Unmanaged CDP shortcut(s) exist for this port; add -Force to include them.' }
        Emit $R 0
    }

    $removedS = New-Object System.Collections.Generic.List[string]
    foreach ($it in $items) {
        try { Remove-Item -LiteralPath $it.Path -Force -ErrorAction Stop; $removedS.Add($it.Path) }
        catch { Warn "Could not delete $($it.Path): $($_.Exception.Message)" }
    }
    $removedI = New-Object System.Collections.Generic.List[string]
    foreach ($f in $icons) { Remove-Item -LiteralPath $f -Force; $removedI.Add($f) }

    $removedP = New-Object System.Collections.Generic.List[string]
    $kept = New-Object System.Collections.Generic.List[string]
    if ($Purge) {
        if ($running.Count -gt 0) {
            Warn "Chrome on port $port is still running; profile directory NOT deleted. Run: stop $port, then remove $port -Purge."
            foreach ($pd in $existingProfiles) { $kept.Add($pd) }
        } else {
            foreach ($pd in $existingProfiles) {
                $full = [IO.Path]::GetFullPath($pd)
                $inRoot = $full.StartsWith([IO.Path]::GetFullPath($ProfileRoot), [StringComparison]::OrdinalIgnoreCase)
                if (-not $inRoot -and -not $Force) {
                    Warn "Profile $full is outside $ProfileRoot; not deleting without -Force."
                    $kept.Add($full)
                    continue
                }
                Remove-Item -LiteralPath $full -Recurse -Force
                $removedP.Add($full)
            }
        }
    } else {
        foreach ($pd in $existingProfiles) { $kept.Add($pd) }
    }
    Refresh-IconCache

    $R.removed_shortcuts = @($removedS)
    $R.removed_icons     = @($removedI)
    $R.removed_profiles  = @($removedP)
    $R.kept_profiles     = @($kept)
    if ($kept.Count -gt 0 -and -not $Purge) { $R.hint = 'Profile(s) kept (login state, cookies). Add -Purge to delete them.' }
    if ($items.Count -eq 0) {
        if ($unmanaged.Count -gt 0) { $R.hint = 'Only unmanaged CDP shortcut(s) exist for this port; add -Force to remove them.' }
        elseif ($removedI.Count -eq 0 -and $removedP.Count -eq 0) { $R.hint = "Nothing to remove for port $port." }
    }
    Emit $R 0
}

# ---------------------------------------------------------------- dispatch
try {
    switch ($Action) {
        'help'   { Show-Help; exit 0 }
        'path'   { Invoke-Path }
        'list'   { Invoke-List }
        'add'    { Invoke-Add    (Resolve-Port $Port) }
        'status' { Invoke-Status (Resolve-Port $Port) }
        'launch' { $r = @(Invoke-Launch (Resolve-Port $Port) $false)[-1]; Emit $r $script:ExitCode }
        'stop'   { Invoke-Stop   (Resolve-Port $Port) }
        'remove' { Invoke-Remove (Resolve-Port $Port) }
    }
} catch {
    Fail $Action $_.Exception.Message $null 1 $null
}
