"""Create a caption-first case study from the existing, verified Notepad capture.

No model outputs are fabricated. 00:14–00:35 is one continuous source trim.
Requires existing Pillow, FFmpeg, FFprobe; does not install or call an API.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EXPECTED_SOURCE_SHA256 = "2bd15e5cd09b7537292804a63e20e2326573f69bb498c7dd129e5ed0c1180383"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True, help="Existing original Notepad capture")
parser.add_argument("--repo", type=Path, required=True, help="Prompt Rewriter checkout")
parser.add_argument(
    "--workdir", type=Path, required=True, help="Directory for rendering intermediates"
)
args = parser.parse_args()
HERE, REPO, SOURCE = args.workdir.resolve(), args.repo.resolve(), args.source.resolve()
HERE.mkdir(parents=True, exist_ok=True)
W, H = 1920, 1080
BG, CARD, INK, MUTED, ACCENT = "#0C1420", "#152232", "#F4F3EC", "#AEBBC7", "#BBE58B"


def font(n, bold=False, mono=False):
    name = "consola.ttf" if mono else ("segoeuib.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(Path(r"C:\Windows\Fonts") / name), n)


def base(chapter, label):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((80, 68, 112, 100), radius=9, fill=ACCENT)
    d.text((130, 61), "PROMPT REWRITER", font=font(27, True), fill=INK)
    d.text((80, 984), chapter, font=font(24), fill=MUTED)
    d.text((1840, 984), label, font=font(24), anchor="ra", fill=MUTED)
    d.line((80, 948, 1840, 948), fill="#2A3A4B", width=2)
    return im, d


def text(d, xy, value, size=42, color=INK, bold=False, spacing=16):
    d.multiline_text(xy, value, font=font(size, bold), fill=color, spacing=spacing)


def pill(d, xy, value):
    x, y = xy
    width = d.textbbox((0, 0), value, font=font(25, True))[2] + 44
    d.rounded_rectangle((x, y, x + width, y + 49), radius=24, fill="#243C30")
    d.text((x + 22, y + 8), value, font=font(25, True), fill=ACCENT)


def save(im, name):
    p = HERE / (name + ".png")
    im.save(p)
    return p


def slides():
    im, d = base("01 / THE IDEA", "WINDOWS DESKTOP MVP")
    pill(d, (80, 183), "LOCAL OLLAMA RUN")
    text(d, (80, 286), "A rough request.\nA clearer prompt.", 92, bold=True, spacing=9)
    text(
        d,
        (85, 567),
        "Select text in Notepad, use one hotkey,\nand keep working in the same field.",
        43,
        color=MUTED,
    )
    d.rounded_rectangle((80, 775, 691, 857), radius=18, outline="#536453", width=2)
    text(d, (111, 791), "Ctrl  +  Shift  +  Space", 36, color=ACCENT, bold=True)
    save(im, "01-intro")

    im, d = base("02 / THE REQUEST", "SYNTHETIC EXAMPLE")
    text(d, (80, 171), "Start with what you know.", 66, bold=True)
    d.rounded_rectangle((80, 303, 1840, 782), radius=24, fill=CARD)
    text(
        d,
        (126, 348),
        "make me a 4-week Python plan for data science;\n"
        "I am a beginner, can study 45 minutes a day,\n"
        "and want one mini-project each week",
        49,
        spacing=26,
    )
    text(d, (126, 669), "Original wording from the source recording", 28, color=MUTED)
    text(
        d,
        (80, 840),
        "Goal  /  experience  /  available time  /  weekly deliverable",
        31,
        color=ACCENT,
    )
    save(im, "02-request")

    im, d = base("03 / THE ACTUAL DESKTOP RUN", "CONTINUOUS FOOTAGE · NORMAL SPEED")
    pill(d, (1440, 61), "OLLAMA · LOCAL")
    text(d, (80, 170), "One field, from selection to result.", 63, bold=True)
    d.rounded_rectangle((77, 297, 1843, 809), radius=14, fill="#344B57")
    text(
        d,
        (80, 844),
        "The source wait is preserved. No speed-up or output substitution.",
        30,
        color=MUTED,
    )
    save(im, "03-live")

    im, d = base("04 / READ THE RESULT", "EXACT TRANSCRIPT · EDITORIAL LINE BREAKS")
    text(d, (80, 162), "Five sections. One usable prompt.", 61, bold=True)
    fields = [
        ("ROLE", "Data Science Educator"),
        ("CONTEXT", "Beginner"),
        (
            "CONCRETE TASK",
            "Create a 4-week Python plan for data science, tailored for a beginner\n"
            "studying 45 minutes a day, with one mini-project per week",
        ),
        ("CONSTRAINTS", "Use only supplied facts; state assumptions explicitly"),
        ("OUTPUT FORMAT", "Weekly plan with project details and study schedule"),
    ]
    ys = [286, 393, 500, 660, 767]
    for (label, value), y in zip(fields, ys, strict=True):
        text(d, (84, y), label, 24, color=ACCENT, bold=True)
        text(d, (430, y - 4), value, 35, spacing=13)
        d.line(
            (
                80,
                y + 78 if label != "CONCRETE TASK" else y + 131,
                1840,
                y + 78 if label != "CONCRETE TASK" else y + 131,
            ),
            fill="#263747",
            width=1,
        )
    save(im, "04-result")

    im, d = base(
        "05 / WHAT THE CODE CHECKS", "ARCHITECTURE EXPLANATION · NOT EXTRA CAPTURED BEHAVIOR"
    )
    text(d, (80, 158), "A guarded copy → rewrite → paste.", 61, bold=True)
    stages = [
        ("01", "Check selection", "Empty, oversized and already\nstructured text can stop here."),
        ("02", "Get a valid result", "Configured provider order;\nstrict five-field validation."),
        ("03", "Re-check the desktop", "Focus, target text and\nclipboard must still be safe."),
        ("04", "Send paste", "Then restore the prior plain-\ntext clipboard when safe."),
    ]
    for i, (n, title, desc) in enumerate(stages):
        x = 80 + i * 448
        d.rounded_rectangle((x, 334, x + 416, 650), radius=20, fill=CARD)
        text(d, (x + 28, 359), n, 31, color=ACCENT, bold=True)
        text(d, (x + 28, 421), title, 32, bold=True)
        text(d, (x + 28, 488), desc, 27, color=MUTED, spacing=12)
        if i < 3:
            text(d, (x + 424, 462), "→", 27, color=ACCENT)
    d.rounded_rectangle((80, 705, 1840, 856), radius=20, fill="#332A26")
    text(d, (110, 727), "Changed focus, changed clipboard or unusable response?", 33, bold=True)
    text(
        d,
        (110, 783),
        "The workflow can cancel before pasting. These paths are covered by tests.",
        30,
        color="#E0BA9E",
    )
    save(im, "05-checks")

    im, d = base("06 / SCOPE & SOURCE", "CAPTIONED CASE STUDY · RE-EDITED OCTOBER 2026")
    text(d, (80, 171), "Small tool. Clear boundaries.", 70, bold=True)
    text(
        d,
        (80, 314),
        "01  Real Notepad recording, reused from the existing local demo\n"
        "02  One uninterrupted selection-to-result sequence\n"
        "03  Local route shown; no cloud inference claimed",
        36,
        spacing=24,
    )
    text(
        d,
        (80, 566),
        "This is a Windows MVP. Clipboard recovery is plain-text and best effort.\n"
        "Structural validation does not prove factual accuracy or app compatibility.",
        32,
        color=MUTED,
        spacing=15,
    )
    pill(d, (80, 730), "READ THE CODE + WATCH THE UNCUT TAKE")
    text(d, (80, 815), "github.com/Zinga18018/prompt-rewriter", 35, color=ACCENT)
    save(im, "06-outro")


def run(args):
    subprocess.run(args, check=True)


def render():
    ff = shutil.which("ffmpeg")
    assert ff, "FFmpeg required"
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != EXPECTED_SOURCE_SHA256:
        raise ValueError(
            "Source differs from the verified capture; "
            "review footage and transcripts before editing."
        )
    durations = [7, 7, 21, 13, 12, 8]
    names = ["01-intro", "02-request", "03-live", "04-result", "05-checks", "06-outro"]
    for name, duration in zip(names, durations, strict=True):
        out = HERE / (name + ".mp4")
        args = [
            ff,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            str(HERE / (name + ".png")),
        ]
        if name == "03-live":
            args += ["-ss", "10", "-t", "21", "-i", str(SOURCE)]
            vf = (
                "[1:v]crop=1220:350:0:0,scale=1752:502:flags=lanczos,setsar=1[s];"
                "[0:v][s]overlay=84:302:shortest=1,format=yuv420p[v]"
            )
            args += ["-filter_complex", vf, "-map", "[v]"]
        else:
            args += [
                "-vf",
                f"fade=t=in:st=0:d=0.22,fade=t=out:st={duration - 0.22}:d=0.22,format=yuv420p",
            ]
        args += [
            "-an",
            "-t",
            str(duration),
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-threads",
            "4",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ]
        run(args)
    concat = HERE / "segments.txt"
    concat.write_text(
        "\n".join("file '" + str(HERE / (n + ".mp4")).replace("\\", "/") + "'" for n in names),
        encoding="utf-8",
    )
    final = REPO / "assets" / "prompt-rewriter-case-study.mp4"
    run(
        [
            ff,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(final),
        ]
    )
    shutil.copy2(final, HERE / final.name)
    shutil.copy2(HERE / "01-intro.png", REPO / "assets" / "prompt-rewriter-case-study-poster.png")
    # A standalone uninterrupted source trim is preserved separately.
    continuous = HERE / "prompt-rewriter-continuous-take.mp4"
    run(
        [
            ff,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-ss",
            "10",
            "-i",
            str(SOURCE),
            "-t",
            "21",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(continuous),
        ]
    )
    manifest = {
        "source_path": str(SOURCE),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "source_duration_seconds": 37.666667,
        "source_verified_by": (
            "Visual inspection of sampled source frames and exact result transcript; "
            "repository README and scripts document local Ollama provenance."
        ),
        "new_recording": False,
        "cloud_requests": 0,
        "demo_duration_seconds": 68,
        "continuous_segment": {
            "output_start": 14,
            "output_end": 35,
            "source_start": 10,
            "source_end": 31,
            "speed": 1.0,
            "crop": [0, 0, 1220, 350],
        },
        "narration": "None; caption-first silent video.",
        "claim_limits": (
            "Local demo provenance is documented by original project. "
            "Footage itself does not expose a provider log. "
            "Not a latency benchmark or cross-app compatibility proof."
        ),
        "output_sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
    }
    (HERE / "provenance.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    slides()
    render()
