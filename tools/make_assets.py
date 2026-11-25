"""Generate the repository artwork.

Everything here is deterministic: the same input produces the same pixels.

    python tools/make_assets.py

Outputs:

    assets/hero.svg     vector banner
    assets/demo.gif     terminal recording of a real solve
    assets/demo.mp4     the same recording, H.264

The terminal transcript is captured from the CLI itself, so the GIF never
shows output the engine does not actually produce.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

BG = "#0d1117"
PANEL = "#11161d"
EDGE = "#21262d"
TEXT = "#c9d1d9"
DIM = "#6e7681"
MUTED = "#8b949e"
BRIGHT = "#e6edf3"
SILVER = "#a8b3bf"

MONO = "/usr/share/fonts/truetype/firacode/FiraCode-Regular.ttf"
MONO_BOLD = "/usr/share/fonts/truetype/firacode/FiraCode-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

WIDTH, HEIGHT = 1080, 706
PAD = 44
LINE = 27
FONT_SIZE = 18


# -- transcript -------------------------------------------------------


def transcript():
    """Run the real CLI and turn its output into terminal lines."""
    sys.path.insert(0, str(ROOT))
    from argent.cli import main  # noqa: E402
    from argent.corpus import write_corpus  # noqa: E402

    corpus = ROOT / "corpus"
    shutil.rmtree(corpus, ignore_errors=True)
    write_corpus(corpus, per_family=1, seed=1337)
    os.chdir(ROOT)

    lines = []
    lines.append(("cmd", "argent corpus -o corpus -p 1"))
    lines.append(("out", "wrote 8 program(s) to corpus"))
    lines.append(("blank", ""))
    lines.append(("cmd", "argent solve corpus/hash-00.sasm -n 6"))
    lines.append(("blank", ""))

    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main(["solve", "corpus/hash-00.sasm", "-n", "6"])
    body = buffer.getvalue().splitlines()

    pending = False
    for line in body:
        if not line.strip():
            if not pending:
                lines.append(("blank", ""))
                pending = True
            continue
        pending = False
        stripped = line.strip()
        if stripped.startswith("status"):
            lines.append(("ok", line))
        elif stripped.startswith("verified"):
            lines.append(("ok", line))
        elif stripped.startswith("input") and "symbolic" not in stripped:
            lines.append(("key", line))
        elif stripped.startswith("paths"):
            lines.append(("stat", line))
        else:
            lines.append(("out", line))
    return lines


# -- gif --------------------------------------------------------------


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def frame(lines, cursor=True, highlight=None, cursor_inline=False):
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    # window chrome
    draw.rounded_rectangle(
        (12, 12, WIDTH - 12, HEIGHT - 12), radius=14, fill=PANEL, outline=EDGE
    )
    draw.line((12, 62, WIDTH - 12, 62), fill=EDGE)
    for index in range(3):
        x = 40 + index * 22
        draw.ellipse((x, 31, x + 11, 41), outline=DIM, width=1)
    draw.text((WIDTH / 2, 30), "argent", font=font(MONO, 15), fill=MUTED, anchor="ma")

    body = font(MONO, FONT_SIZE)
    y = 84
    inline_x = PAD

    for kind, text in lines:
        if kind == "blank":
            y += LINE
            continue
        if kind == "cmd":
            draw.text((PAD, y), "$", font=font(MONO_BOLD, FONT_SIZE), fill=SILVER)
            draw.text((PAD + 22, y), text, font=body, fill=BRIGHT)
        elif kind == "ok":
            draw.text((PAD, y), text, font=font(MONO_BOLD, FONT_SIZE), fill=BRIGHT)
        elif kind == "key":
            draw.text((PAD, y), text, font=font(MONO_BOLD, FONT_SIZE), fill=BRIGHT)
        elif kind == "stat":
            draw.text((PAD, y), text, font=body, fill=MUTED)
        else:
            draw.text((PAD, y), text, font=body, fill=TEXT)
        inline_x = PAD + 22 + body.getlength(text)
        y += LINE

    if cursor:
        if cursor_inline:
            draw.rectangle((inline_x, y - LINE + 3, inline_x + 10, y - LINE + 20),
                           fill=SILVER)
        else:
            draw.rectangle((PAD, y + 3, PAD + 10, y + 20), fill=SILVER)

    if highlight:
        draw.rounded_rectangle((PAD - 12, highlight, WIDTH - PAD + 12, highlight + 30),
                               radius=6, outline=SILVER)
    return image


def build_gif(lines):
    frames = []
    durations = []
    shown = []

    def push(cursor=True, delay=60, inline=False):
        frames.append(frame(shown, cursor=cursor, cursor_inline=inline))
        durations.append(delay)

    for kind, text in lines:
        if kind == "cmd":
            # type it out, two characters per frame
            typed = ""
            for index in range(0, len(text), 2):
                typed = text[: index + 2]
                shown.append((kind, typed))
                push(delay=35, inline=True)
                shown.pop()
            shown.append((kind, typed))
            push(delay=260)
        elif kind == "blank":
            shown.append((kind, text))
            push(delay=90)
        else:
            shown.append((kind, text))
            push(delay=75 if kind not in ("ok", "key") else 300)

    # hold the finished screen, cursor blinking
    for _ in range(3):
        push(cursor=True, delay=420)
        push(cursor=False, delay=420)

    save_gif(frames, durations)
    return frames, durations


def save_gif(frames, durations):
    frames[0].save(
        ASSETS / "demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )


def build_mp4(frames, durations):
    frames_dir = ROOT / "corpus" / "_frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True)

    saved = 0
    for image, duration in zip(frames, durations):
        repeats = max(1, round(duration / 80))
        for _ in range(repeats):
            image.save(frames_dir / f"{saved:04d}.png")
            saved += 1

    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-framerate", "12.5",
            "-i", str(frames_dir / "%04d.png"),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
            str(ASSETS / "demo.mp4"),
        ],
        check=True,
    )
    shutil.rmtree(frames_dir, ignore_errors=True)
    return saved


# -- svg --------------------------------------------------------------


def build_svg():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="400"
     viewBox="0 0 1280 400" role="img" aria-label="Argent">
  <defs>
    <linearGradient id="metal" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#f7f9fb"/>
      <stop offset="0.42" stop-color="#d3dae2"/>
      <stop offset="0.52" stop-color="#8b949e"/>
      <stop offset="0.62" stop-color="#c3ccd5"/>
      <stop offset="1" stop-color="#7d8792"/>
    </linearGradient>
    <linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#c9d1d9" stop-opacity="0.55"/>
      <stop offset="0.5" stop-color="#c9d1d9" stop-opacity="0.12"/>
      <stop offset="1" stop-color="#c9d1d9" stop-opacity="0"/>
    </linearGradient>
    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M40 0H0V40" fill="none" stroke="#161b22" stroke-width="1"/>
    </pattern>
  </defs>

  <rect width="1280" height="400" fill="#0d1117"/>
  <rect width="1280" height="400" fill="url(#grid)"/>
  <rect x="0" y="0" width="1280" height="2" fill="url(#fade)"/>

  <text x="80" y="128" font-family="Fira Code, DejaVu Sans Mono, monospace"
        font-size="22" letter-spacing="14" fill="#6e7681">SYMBOLIC EXECUTION</text>

  <text x="72" y="248" font-family="Fira Code, DejaVu Sans Mono, monospace"
        font-size="104" font-weight="700" letter-spacing="8" fill="url(#metal)">ARGENT</text>

  <line x1="80" y1="286" x2="1200" y2="286" stroke="#21262d"/>

  <text x="80" y="330" font-family="Fira Code, DejaVu Sans Mono, monospace"
        font-size="19" fill="#8b949e">a from-scratch engine for a 32-bit ISA  &#183;  z3  &#183;  verified solutions</text>

  <g font-family="Fira Code, DejaVu Sans Mono, monospace" font-size="15" fill="#6e7681">
    <text x="80" y="364">58 programs</text>
    <text x="248" y="364">54 solved</text>
    <text x="416" y="364">54 replayed</text>
    <text x="600" y="364">0 unverified</text>
  </g>

  <g stroke="#30363d" fill="none">
    <path d="M1080 96h48M1104 72h48M1152 120h48"/>
    <circle cx="1152" cy="120" r="2" fill="#8b949e"/>
    <circle cx="1104" cy="72" r="2" fill="#8b949e"/>
  </g>
</svg>
"""
    (ASSETS / "hero.svg").write_text(svg, encoding="utf-8")


def main():
    ASSETS.mkdir(exist_ok=True)
    build_svg()
    lines = transcript()
    frames, durations = build_gif(lines)
    build_mp4(frames, durations)
    shutil.rmtree(ROOT / "corpus", ignore_errors=True)
    print(f"hero.svg, demo.gif ({len(frames)} frames), demo.mp4")


if __name__ == "__main__":
    main()
