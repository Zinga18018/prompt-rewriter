$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$assetsDir = Join-Path $projectRoot "assets"
$sourceVideo = Join-Path $projectRoot "prompt-rewriter-capture-v2.mp4"
$backgroundImage = Join-Path $assetsDir "cinematic-background.png"
$overlayFile = Join-Path $PSScriptRoot "demo-overlay.ass"
$outputVideo = Join-Path $assetsDir "prompt-rewriter-cinematic.mp4"
$posterImage = Join-Path $assetsDir "prompt-rewriter-poster.png"
$previewGif = Join-Path $assetsDir "prompt-rewriter-preview.gif"

$ffmpeg = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter "ffmpeg.exe" -Recurse -ErrorAction Stop |
    Select-Object -First 1 -ExpandProperty FullName

if (-not (Test-Path -LiteralPath $sourceVideo)) {
    throw "Missing source capture: $sourceVideo"
}

if (-not (Test-Path -LiteralPath $backgroundImage)) {
    throw "Missing cinematic background: $backgroundImage"
}

New-Item -ItemType Directory -Force -Path $assetsDir | Out-Null

# The screen capture is split into three honest moments: rough text, the selected
# text, and the finished result. A two-second held frame removes tool-orchestration
# delay from the demo without pretending inference happened faster than recorded.
$videoFilter = @"
[1:v]scale=2100:1182:flags=lanczos,crop=1920:1080:x='90+25*sin(t*0.16)':y='51+18*cos(t*0.13)',eq=brightness=-0.18:contrast=1.10:saturation=0.90,boxblur=1:1,setpts=PTS-STARTPTS,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.18:t=fill[bg];
[0:v]trim=start=10:end=14,setpts=PTS-STARTPTS,crop=1424:500:0:0,scale=1700:596:flags=lanczos,format=yuva420p,fade=t=in:st=0:d=0.25:alpha=1,fade=t=out:st=3.75:d=0.25:alpha=1,setpts=PTS+4/TB[rough];
[0:v]trim=start=14:end=16,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=2,crop=1424:500:0:0,scale=1700:596:flags=lanczos,format=yuva420p,fade=t=in:st=0:d=0.25:alpha=1,fade=t=out:st=3.75:d=0.25:alpha=1,setpts=PTS+8/TB[selected];
[0:v]trim=start=24:end=31,setpts=PTS-STARTPTS,crop=1424:500:0:0,scale=1700:596:flags=lanczos,format=yuva420p,fade=t=in:st=0:d=0.25:alpha=1,fade=t=out:st=6.75:d=0.25:alpha=1,setpts=PTS+12/TB[result];
[bg]drawbox=x=82:y=294:w=1756:h=632:color=black@0.42:t=fill:enable='between(t,3.95,19.05)',drawbox=x=96:y=286:w=1728:h=624:color=black@0.78:t=fill:enable='between(t,3.95,19.05)',drawbox=x=98:y=288:w=1724:h=620:color=0x66D9FF@0.62:t=2:enable='between(t,3.95,19.05)',drawbox=x=110:y=296:w=1700:h=4:color=0x6AE0FF@0.82:t=fill:enable='between(t,3.95,19.05)'[card];
[card][rough]overlay=x=110:y=300:eof_action=pass:shortest=0[v1];
[v1][selected]overlay=x=110:y=300:eof_action=pass:shortest=0[v2];
[v2][result]overlay=x=110:y=300:eof_action=pass:shortest=0[v3];
[v3]drawbox=x=110:y=598:w=1700:h=3:color=0x6AE0FF@0.62:t=fill:enable='between(t,10,12)',vignette=angle=PI/5:eval=frame,ass='scripts/demo-overlay.ass',fps=30,format=yuv420p[vout];
[2:a]volume=0.032,lowpass=f=220,afade=t=in:st=0:d=1.6,afade=t=out:st=22:d=2[bed1];
[3:a]volume=0.014,lowpass=f=320,afade=t=in:st=0:d=1.6,afade=t=out:st=22:d=2[bed2];
[4:a]volume=0.11,afade=t=out:st=0.02:d=0.06,adelay=8200|8200[click];
[5:a]volume=0.065,afade=t=out:st=0.08:d=0.62,adelay=12000|12000[chime1];
[6:a]volume=0.040,afade=t=out:st=0.10:d=0.72,adelay=12080|12080[chime2];
[7:a]volume=0.035,afade=t=out:st=0.10:d=0.85,adelay=19300|19300[out1];
[8:a]volume=0.025,afade=t=out:st=0.12:d=1.00,adelay=19420|19420[out2];
[bed1][bed2][click][chime1][chime2][out1][out2]amix=inputs=7:duration=longest:normalize=0,volume=15dB,alimiter=limit=0.90[aout]
"@

$renderArgs = @(
    "-hide_banner", "-y",
    "-i", $sourceVideo,
    "-framerate", "30", "-loop", "1", "-i", $backgroundImage,
    "-f", "lavfi", "-i", "sine=frequency=55:sample_rate=48000:duration=24",
    "-f", "lavfi", "-i", "sine=frequency=110:sample_rate=48000:duration=24",
    "-f", "lavfi", "-i", "sine=frequency=1320:sample_rate=48000:duration=0.08",
    "-f", "lavfi", "-i", "sine=frequency=659.25:sample_rate=48000:duration=0.70",
    "-f", "lavfi", "-i", "sine=frequency=987.77:sample_rate=48000:duration=0.82",
    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.95",
    "-f", "lavfi", "-i", "sine=frequency=659.25:sample_rate=48000:duration=1.12",
    "-filter_complex", $videoFilter,
    "-map", "[vout]", "-map", "[aout]",
    "-t", "24", "-r", "30",
    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
    "-movflags", "+faststart",
    $outputVideo
)

Push-Location $projectRoot
try {
    & $ffmpeg @renderArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Cinematic MP4 render failed with exit code $LASTEXITCODE"
    }

    & $ffmpeg -hide_banner -y -ss 13.6 -i $outputVideo -frames:v 1 -update 1 -compression_level 8 $posterImage
    if ($LASTEXITCODE -ne 0) {
        throw "Poster extraction failed with exit code $LASTEXITCODE"
    }

    # The preview intentionally stops after the result appears. Restricting the
    # palette, frame rate, and duration keeps it practical for a GitHub README.
    $gifFilter = "fps=8,scale=800:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=56:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
    & $ffmpeg -hide_banner -y -t 16 -i $outputVideo -filter_complex $gifFilter -loop 0 $previewGif
    if ($LASTEXITCODE -ne 0) {
        throw "GIF preview render failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Get-Item $outputVideo, $posterImage, $previewGif |
    Select-Object Name, Length, LastWriteTime
