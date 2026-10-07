#!/usr/bin/env python3
"""
textcrawl.py - Star Wars-style opening crawl, rendered to an animated GIF.

The crawl text lives in a plain text file, not in this script:

    python3 textcrawl.py mytext.txt
    python3 textcrawl.py mytext.txt -o session12.gif --frames 800
    python3 textcrawl.py --selftest          # run the built-in tests on toy text

Text file format:
    * One line in the file = one forced line break in the crawl.
    * A blank line = a paragraph gap.
    * Long lines are word-wrapped automatically.
    * UTF-8 (so curly quotes and the ellipsis character work).
"""

import argparse
import os
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# --- Defaults (all overridable from the command line) -----------------------
W, H = 900, 600
DEFAULT_FPS = 24
DEFAULT_FRAMES = 640
DEFAULT_FONT_SIZE = 34
DEFAULT_OUTPUT = "party_crawl.gif"

# Try a bold font commonly available on Linux/macOS/Windows.
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

CRAWL_WIDTH = 650              # width of the flat text layer, in pixels
LINE_SPACING = 12              # extra pixels between lines
TEXT_COLOR = (255, 215, 0, 255)

STAGE_H = 1500                 # how much crawl is "on the floor" at once
HORIZON_Y = 110                # where the crawl vanishes near the top
TOP_HALF = 80                  # half-width of the crawl at the horizon
BOT_HALF = 330                 # half-width of the crawl at the bottom

DEBUG = False


def debug(msg):
    """Print a debug line to stderr when --debug is on."""
    if DEBUG:
        print(f"[debug] {msg}", file=sys.stderr)


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


# --- Step 1: read the text file ---------------------------------------------
def read_text_file(path):
    """Read crawl text as UTF-8, with clear errors for the usual mistakes."""
    debug(f"step 1: reading text from {os.path.abspath(path)}")
    if not os.path.isfile(path):
        die(f"text file not found: {path}")
    try:
        # utf-8-sig quietly drops a BOM if a Windows editor added one.
        with open(path, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    except UnicodeDecodeError as exc:
        die(f"{path} is not valid UTF-8 ({exc}). Re-save it as UTF-8.")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text.strip():
        die(f"text file is empty: {path}")
    debug(f"step 1: read {len(text)} chars, {text.count(chr(10)) + 1} raw lines")
    return text


# --- Step 2: load a font ----------------------------------------------------
def load_font(size):
    """Return (font, line_height). Falls back to Pillow's default font."""
    for path in FONT_PATHS:
        try:
            font = ImageFont.truetype(path, size)
            debug(f"step 2: using font {path} at {size}px")
            break
        except OSError:
            debug(f"step 2: font not found: {path}")
    else:
        try:
            font = ImageFont.load_default(size=size)   # Pillow >= 10.1
            debug("step 2: using Pillow default font (scalable)")
        except TypeError:
            font = ImageFont.load_default()            # older Pillow: tiny bitmap
            print("WARNING: no TrueType font found and Pillow is old; "
                  "text will be very small. Install fonts-dejavu-core.",
                  file=sys.stderr)
    # Old bitmap fonts have no .size, so measure a tall glyph pair instead.
    probe = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), "Ay", font=font)
    line_height = max(getattr(font, "size", 0), probe[3] - probe[1])
    debug(f"step 2: line height = {line_height}px")
    return font, line_height


# --- Step 3: wrap and render the text onto a transparent layer --------------
def wrap_lines(text, font, max_width):
    """Word-wrap each line of the file to fit max_width pixels."""
    draw = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                line = candidate
            else:
                if line:                     # don't emit an empty line when a
                    lines.append(line)       # single word is wider than the box
                else:
                    print(f"WARNING: word too wide for the crawl: {word!r}",
                          file=sys.stderr)
                line = word
        if line:
            lines.append(line)
    debug(f"step 3: wrapped into {len(lines)} lines")
    return lines


def render_text_layer(text, font, line_height):
    """Render the crawl text; the canvas is sized to fit, so nothing clips."""
    lines = wrap_lines(text, font, CRAWL_WIDTH - 50)
    top_pad, bottom_pad = 30, 40
    height = top_pad + len(lines) * (line_height + LINE_SPACING) + bottom_pad
    layer = Image.new("RGBA", (CRAWL_WIDTH, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    y = top_pad
    for line in lines:
        if line:
            box = draw.textbbox((0, 0), line, font=font)
            x = (CRAWL_WIDTH - (box[2] - box[0])) // 2
            draw.text((x, y), line, fill=TEXT_COLOR, font=font)
        y += line_height + LINE_SPACING
    debug(f"step 3: text layer is {layer.width}x{layer.height}px")
    # Sanity check: something was actually drawn.
    if layer.getbbox() is None:
        die("rendered text layer is blank - check the font and text file")
    return layer, lines


# --- Step 4: perspective transform ------------------------------------------
# We lay the text onto a flat "stage" and project that stage onto a trapezoid
# on screen (wide at the bottom, narrow at the horizon). A single perspective
# transform makes the lines both converge AND compress vertically toward the
# top, which gives the correct receding-into-distance look.
def find_coeffs(target, source):
    """Coefficients to warp `source` corners onto `target` corners."""
    matrix = []
    for t, s in zip(target, source):
        matrix.append([s[0], s[1], 1, 0, 0, 0, -t[0] * s[0], -t[0] * s[1]])
        matrix.append([0, 0, 0, s[0], s[1], 1, -t[1] * s[0], -t[1] * s[1]])
    A = np.array(matrix, dtype=float)
    B = np.array(target, dtype=float).reshape(8)
    return np.linalg.solve(A, B).tolist()


def perspective_coeffs():
    cx = W // 2
    stage_corners = [(0, 0), (CRAWL_WIDTH, 0), (CRAWL_WIDTH, STAGE_H), (0, STAGE_H)]
    screen_trapezoid = [
        (cx - TOP_HALF, HORIZON_Y),
        (cx + TOP_HALF, HORIZON_Y),
        (cx + BOT_HALF, H),
        (cx - BOT_HALF, H),
    ]
    # PIL's PERSPECTIVE maps each OUTPUT (screen) pixel back to an INPUT
    # (stage) coordinate, so we solve for the screen -> stage mapping.
    return find_coeffs(stage_corners, screen_trapezoid)


# --- Step 5: build the frames and save the GIF ------------------------------
def build_gif(text_layer, output, frames_total, fps):
    coeffs = perspective_coeffs()
    total_scroll = STAGE_H + text_layer.height     # fully below -> fully above
    px_per_frame = total_scroll / max(frames_total - 1, 1)
    debug(f"step 5: {frames_total} frames, {total_scroll}px of scroll "
          f"({px_per_frame:.1f}px/frame), {frames_total / fps:.1f}s long")
    if px_per_frame > 12:
        print(f"NOTE: scrolling {px_per_frame:.1f}px per frame - a long text "
              f"may look rushed. Try --frames {int(total_scroll / 5)}.",
              file=sys.stderr)

    frames = []
    for frame_no in range(frames_total):
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 255))

        # Subtle star field.
        star_draw = ImageDraw.Draw(frame)
        for i in range(120):
            x = (i * 83 + frame_no * 2) % W
            y_star = (i * 47) % H
            b = 100 + ((i * 31) % 155)
            star_draw.point((x, y_star), fill=(b, b, b, 255))

        # Scroll the text up through the stage (bottom = near viewer).
        progress = frame_no / max(frames_total - 1, 1)
        paste_y = STAGE_H - int(progress * total_scroll)

        stage = Image.new("RGBA", (CRAWL_WIDTH, STAGE_H), (0, 0, 0, 0))
        stage.paste(text_layer, (0, paste_y), text_layer)
        warped = stage.transform((W, H), Image.PERSPECTIVE, coeffs,
                                 resample=Image.BILINEAR)

        frame = Image.alpha_composite(frame, warped)
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE))
        if DEBUG and frame_no % 100 == 0:
            debug(f"step 5: frame {frame_no}/{frames_total}")

    frames[0].save(output, save_all=True, append_images=frames[1:],
                   duration=1000 // fps, loop=0, optimize=False)

    # Sanity check: the GIF exists, opens, and has the right frame count.
    if not os.path.isfile(output) or os.path.getsize(output) == 0:
        die(f"output was not written: {output}")
    with Image.open(output) as gif:
        n = getattr(gif, "n_frames", 1)
        if n != frames_total or gif.size != (W, H):
            die(f"output check failed: {n} frames at {gif.size}, "
                f"expected {frames_total} at {(W, H)}")
    debug(f"step 5: verified {output} ({os.path.getsize(output):,} bytes)")


def make_crawl(text_path, output, frames_total, fps, font_size):
    text = read_text_file(text_path)
    font, line_height = load_font(font_size)
    layer, _ = render_text_layer(text, font, line_height)
    build_gif(layer, output, frames_total, fps)
    print(f"Created {output}")


# --- Self-test on toy data --------------------------------------------------
def selftest():
    """Small, fast checks on throwaway text. Writes only to a temp folder."""
    global DEBUG
    print("Running self-test...")
    font, lh = load_font(DEFAULT_FONT_SIZE)
    passed = 0

    def check(cond, name):
        nonlocal passed
        if not cond:
            die(f"self-test FAILED: {name}")
        passed += 1
        print(f"  ok  {name}")

    # 1. Wrapping keeps every word, in order, and fits the width.
    toy = "The quick brown fox jumps over the lazy dog " * 6
    lines = wrap_lines(toy, font, CRAWL_WIDTH - 50)
    check(" ".join(lines).split() == toy.split(), "wrapping keeps all words in order")
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    check(all(probe.textbbox((0, 0), l, font=font)[2] <= CRAWL_WIDTH - 50
              for l in lines if " " in l), "wrapped lines fit the crawl width")

    # 2. Blank lines become paragraph gaps.
    lines = wrap_lines("Alpha\n\nBeta", font, CRAWL_WIDTH - 50)
    check(lines == ["Alpha", "", "Beta"], "blank line becomes a paragraph gap")

    # 3. A word wider than the box doesn't create a stray empty line.
    lines = wrap_lines("W" * 80, font, CRAWL_WIDTH - 50)
    check(lines == ["W" * 80], "over-wide word does not add an empty line")

    # 4. Long text grows the canvas instead of being clipped (old 1800px cap).
    long_text = "\n\n".join(f"Paragraph {i} of a very long session recap." for i in range(60))
    layer, lines = render_text_layer(long_text, font, lh)
    check(layer.height > 1800, f"long text not clipped (layer {layer.height}px)")
    bottom_band = layer.crop((0, layer.height - 120, CRAWL_WIDTH, layer.height))
    check(bottom_band.getbbox() is not None, "last paragraph is actually drawn")

    with tempfile.TemporaryDirectory() as tmp:
        # 5. File reading: CRLF + BOM are normalised.
        p = os.path.join(tmp, "crlf.txt")
        with open(p, "wb") as fh:
            fh.write("\ufeffLine one\r\n\r\nLine two…\r\n".encode("utf-8"))
        check(read_text_file(p) == "Line one\n\nLine two…", "CRLF/BOM/UTF-8 handled")

        # 6. End-to-end: a tiny GIF with 6 frames.
        out = os.path.join(tmp, "toy.gif")
        make_crawl(p, out, frames_total=6, fps=DEFAULT_FPS, font_size=DEFAULT_FONT_SIZE)
        with Image.open(out) as gif:
            check(gif.n_frames == 6 and gif.size == (W, H), "end-to-end toy GIF")

    print(f"Self-test passed ({passed} checks).")


def main():
    global DEBUG
    ap = argparse.ArgumentParser(
        description="Render a Star Wars-style text crawl from a text file to a GIF.")
    ap.add_argument("text_file", nargs="?", help="UTF-8 text file with the crawl text")
    ap.add_argument("-o", "--output", default=DEFAULT_OUTPUT,
                    help=f"output GIF (default: {DEFAULT_OUTPUT})")
    ap.add_argument("--frames", type=int, default=DEFAULT_FRAMES,
                    help=f"number of frames; more = slower crawl (default: {DEFAULT_FRAMES})")
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS,
                    help=f"frames per second (default: {DEFAULT_FPS})")
    ap.add_argument("--font-size", type=int, default=DEFAULT_FONT_SIZE,
                    help=f"font size in px (default: {DEFAULT_FONT_SIZE})")
    ap.add_argument("--debug", action="store_true", help="print step-by-step diagnostics")
    ap.add_argument("--selftest", action="store_true", help="run built-in tests and exit")
    args = ap.parse_args()
    DEBUG = args.debug

    if args.selftest:
        selftest()
        return
    if not args.text_file:
        ap.error("a text file is required, e.g.  python3 textcrawl.py mytext.txt")
    if args.frames < 2 or args.fps < 1 or args.font_size < 6:
        ap.error("--frames must be >= 2, --fps >= 1, --font-size >= 6")

    make_crawl(args.text_file, args.output, args.frames, args.fps, args.font_size)


if __name__ == "__main__":
    main()
