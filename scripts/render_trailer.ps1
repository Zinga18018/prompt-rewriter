$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$assetsDir = Join-Path $projectRoot "assets"
$sourceVideo = Join-Path $projectRoot "prompt-rewriter-capture-v2.mp4"
$overlayFile = Join-Path $PSScriptRoot "trailer-overlay.ass"
$trailerVideo = Join-Path $assetsDir "prompt-rewriter-trailer.mp4"
$liveDemoVideo = Join-Path $assetsDir "prompt-rewriter-live-demo.mp4"
$trailerPoster = Join-Path $assetsDir "prompt-rewriter-trailer-poster.png"

# FFmpeg is a prerequisite, but no third-party footage, music, or visual plugin is needed.
$ffmpegExe = (Get-Command ffmpeg -ErrorAction Stop).Source
$ffprobeExe = (Get-Command ffprobe -ErrorAction Stop).Source
foreach ($requiredFile in @($sourceVideo, $overlayFile)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Missing required file: $requiredFile"
    }
}

$durationText = (& $ffprobeExe -v error -show_entries format=duration -of "default=noprint_wrappers=1:nokey=1" $sourceVideo)
if ($LASTEXITCODE -ne 0 -or -not $durationText) {
    throw "Could not read source video duration."
}
$sourceDuration = [double]::Parse($durationText.Trim(), [System.Globalization.CultureInfo]::InvariantCulture)
if ($sourceDuration -lt 31.0) {
    throw "Source video must run through at least 31 seconds; found $sourceDuration seconds."
}

New-Item -ItemType Directory -Force -Path $assetsDir | Out-Null

# The trailer is an openly labeled edit. Source 10-12.9 shows rough text;
# 14.033-16.533 shows selection; 23.6-31 shows the result. The last result
# frame is held for the CTA. The actual Notepad recording remains in the proof
# inset throughout, while ASS cards re-typeset its exact words for readability.
# The trailer makes no inference-speed claim from the compressed timeline.
# All visuals, motion accents, and low-key sound use stock FFmpeg.
$trailerFilter = @"
[0:v]drawgrid=w=82:h=82:t=1:c=0x42C98A@0.035,drawbox=x=88:y=150:w=1118:h=786:color=0x10241B@0.96:t=fill,drawbox=x=88:y=150:w=1118:h=786:color=0x56D398@0.42:t=2,drawbox=x=1220:y=150:w=616:h=786:color=0x10241B@0.96:t=fill,drawbox=x=1220:y=150:w=616:h=786:color=0x56D398@0.42:t=2,drawbox=x=88:y=150:w=8:h=786:color=0x73E5AC@0.85:t=fill,drawbox=x=1228:y=320:w=600:h=296:color=0x030805@0.95:t=fill,drawbox=x=1228:y=320:w=600:h=296:color=0x73E5AC@0.72:t=2,drawbox=x=88:y=149:w=1118:h=4:color=0xB0FFD0@0.75:t=fill:enable='between(t,2.84,3.10)+between(t,5.34,5.60)'[bg];
[1:v]trim=start=10:end=12.9,setpts=PTS-STARTPTS,scale=568:276:flags=lanczos,setsar=1[rough];
[1:v]trim=start=14.033333:end=16.533333,setpts=PTS-STARTPTS,scale=568:276:flags=lanczos,setsar=1[selected];
[1:v]trim=start=23.6:end=31,setpts=PTS-STARTPTS,scale=568:276:flags=lanczos,setsar=1,tpad=stop_mode=clone:stop_duration=2.2[result];
[rough][selected][result]concat=n=3:v=1:a=0,fps=30,format=yuv420p[screen];
[bg][screen]overlay=x=1244:y=330:shortest=0:eof_action=repeat,drawbox=x=126:y=340:w=1030:h=1:color=0x70E4AE@0.23:t=fill:enable='gte(t,5.4)',drawbox=x=126:y=443:w=1030:h=1:color=0x70E4AE@0.23:t=fill:enable='gte(t,5.4)',drawbox=x=126:y=629:w=1030:h=1:color=0x70E4AE@0.23:t=fill:enable='gte(t,5.4)',drawbox=x=126:y=742:w=1030:h=1:color=0x70E4AE@0.23:t=fill:enable='gte(t,5.4)',ass=scripts/trailer-overlay.ass,fade=t=out:st=14.55:d=0.45,format=yuv420p[vout];
[2:a]volume=0.021,afade=t=in:st=0:d=0.65,afade=t=out:st=13.8:d=1.2[bed1];
[3:a]volume=0.009,afade=t=in:st=0:d=0.65,afade=t=out:st=13.8:d=1.2[bed2];
[4:a]highpass=f=350,lowpass=f=2400,volume=0.022,afade=t=out:st=0.30:d=0.20,asplit=2[swishA][swishB];
[swishA]adelay=2850:all=1[cut1];
[swishB]adelay=5350:all=1[cut2];
[5:a]volume=0.032,afade=t=out:st=0.30:d=0.55,adelay=12650:all=1[sting];
[bed1][bed2][cut1][cut2][sting]amix=inputs=5:duration=longest:normalize=0,volume=18,alimiter=limit=0.90[aout]
"@

Push-Location $projectRoot
try {
    & $ffmpegExe -hide_banner -y `
        -f lavfi -i "color=c=0x08120f:s=1920x1080:r=30:d=15" `
        -i $sourceVideo `
        -f lavfi -i "sine=frequency=55:sample_rate=48000:duration=15" `
        -f lavfi -i "sine=frequency=82.41:sample_rate=48000:duration=15" `
        -f lavfi -i "anoisesrc=color=pink:sample_rate=48000:duration=0.5" `
        -f lavfi -i "sine=frequency=659.25:sample_rate=48000:duration=0.85" `
        -filter_complex $trailerFilter `
        -map "[vout]" -map "[aout]" `
        -t 15 -r 30 `
        -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p `
        -c:a aac -b:a 160k -ar 48000 `
        -movflags +faststart $trailerVideo
    if ($LASTEXITCODE -ne 0) {
        throw "Trailer render failed with exit code $LASTEXITCODE"
    }

    # A single uninterrupted source trim preserves the recorded delay from
    # selection through replacement. No title cards, speed changes, or held frames.
    & $ffmpegExe -hide_banner -y -i $sourceVideo `
        -vf "trim=start=10:end=31,setpts=PTS-STARTPTS" `
        -an -r 30 -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p `
        -movflags +faststart $liveDemoVideo
    if ($LASTEXITCODE -ne 0) {
        throw "Live demo render failed with exit code $LASTEXITCODE"
    }

    # GitHub's README displays this frame as the clickable trailer preview.
    & $ffmpegExe -hide_banner -y -ss 10 -i $trailerVideo `
        -frames:v 1 -update 1 $trailerPoster
    if ($LASTEXITCODE -ne 0) {
        throw "Trailer poster render failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Get-Item -LiteralPath $trailerVideo, $liveDemoVideo, $trailerPoster |
    Select-Object Name, Length, LastWriteTime
