# statusline-usage: Claude Code status line (PowerShell 5.1 / 7). Reads the
# statusLine JSON on stdin, prints one line. Fail-open: never exits non-zero.
# Output must match statusline.sh byte-for-byte (see SKILL.md).

$ErrorActionPreference = 'SilentlyContinue'
$inv = [System.Globalization.CultureInfo]::InvariantCulture

function Write-Line([string]$text) {
    $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($text + "`n")
    $out = [Console]::OpenStandardOutput()
    $out.Write($bytes, 0, $bytes.Length)
    $out.Flush()
}

function To-Num($v) {
    if ($null -eq $v) { return $null }
    try { return [double]::Parse([string]$v, $inv) } catch { return $null }
}

function Format-Tokens([double]$n) {
    if ($n -lt 1000) { return [string][long][math]::Floor($n) }
    if ($n -lt 1000000) { return ([string][long][math]::Floor($n / 1000)) + 'k' }
    if (($n % 1000000) -eq 0) { return ([string][long]($n / 1000000)) + 'M' }
    $tenths = [long][math]::Floor($n / 100000)
    return ([string][long][math]::Floor($tenths / 10)) + '.' + ([string]($tenths % 10)) + 'M'
}

function Convert-Epoch($secs, [bool]$withDay) {
    $dto = [DateTimeOffset]::FromUnixTimeSeconds([long][math]::Floor($secs))
    $off = $env:STATUSLINE_TZ_OFFSET_MIN
    $parsed = 0
    if ($off -and [int]::TryParse($off.Trim(), [ref]$parsed)) {
        $dto = $dto.ToOffset([TimeSpan]::FromMinutes($parsed))
    } else {
        $dto = $dto.ToLocalTime()
    }
    $fmt = 'HH:mm'
    if ($withDay) { $fmt = 'ddd HH:mm' }
    return $dto.ToString($fmt, $inv)
}

function Build-Line($j, [int]$warn) {
    $parts = New-Object System.Collections.Generic.List[string]

    $model = $j.model.display_name
    if ($model) { $parts.Add([string]$model) }

    $cw = $j.context_window
    if ($null -ne $cw) {
        $cu = $cw.current_usage
        $used = 0.0
        if ($null -ne $cu) {
            foreach ($f in 'input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens') {
                $x = To-Num $cu.$f
                if ($null -ne $x) { $used += $x }
            }
        }
        $size = To-Num $cw.context_window_size
        if ($null -ne $size -and $size -le 0) { $size = $null }
        $pct = To-Num $cw.used_percentage
        if ($null -ne $pct) { $pct = [long][math]::Floor($pct) }
        elseif ($null -ne $size) { $pct = [long][math]::Floor($used * 100 / $size) }
        if (-not ($used -eq 0 -and $null -eq $pct)) {
            $seg = 'ctx ' + (Format-Tokens $used)
            if ($null -ne $size) { $seg += '/' + (Format-Tokens $size) }
            if ($null -ne $pct) { $seg += ' ' + $pct + '%' }
            if ($null -ne $pct -and $pct -ge $warn) { $seg = '!' + $seg }
            $parts.Add($seg)
        }
    }

    $rl = $j.rate_limits
    if ($null -ne $rl) {
        foreach ($w in @(@('five_hour', '5h', $false), @('seven_day', '7d', $true))) {
            $win = $rl.($w[0])
            if ($null -eq $win) { continue }
            $p = To-Num $win.used_percentage
            if ($null -eq $p) { continue }
            $p = [long][math]::Floor($p)
            $seg = $w[1] + ' ' + $p + '%'
            $r = To-Num $win.resets_at
            if ($null -ne $r) { $seg += ' ~' + (Convert-Epoch $r $w[2]) }
            if ($p -ge $warn) { $seg = '!' + $seg }
            $parts.Add($seg)
        }
    }

    return ($parts -join ' | ')
}

$line = ''
try {
    $reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput(), (New-Object System.Text.UTF8Encoding($false)))
    $raw = $reader.ReadToEnd()
    if ($raw -and $raw.Trim()) {
        $warn = 80
        $wv = 0
        if ($env:STATUSLINE_WARN_PCT -and [int]::TryParse($env:STATUSLINE_WARN_PCT.Trim(), [ref]$wv)) { $warn = $wv }
        $j = $raw | ConvertFrom-Json
        if ($null -ne $j) { $line = Build-Line $j $warn }
    }
} catch {
    $line = ''
}
if (-not $line) { $line = 'claude' }
try { Write-Line $line } catch { }
exit 0
