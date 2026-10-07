# textcrawl

A long time ago, in a terminal far, far away… this little Python script turns
any plain text file into a Star Wars–style opening crawl, saved as an animated
GIF. Great for D&D session recaps, birthday invitations, or announcing that the
office coffee machine is broken again.

![demo](demo.gif)

*(The demo is shrunk to half size and a quarter of the frames; real output is
900×600 at 24 fps.)*

## Install

Requires Python 3.8+ and works on Linux, macOS and Windows.

```bash
python3 -m pip install -r requirements.txt
```

On Linux the script looks for DejaVu Sans Bold
(`sudo apt install fonts-dejavu-core` if it's missing); on macOS/Windows it
uses Arial Bold. If none is found it falls back to Pillow's built-in font.

## Usage

```bash
python3 textcrawl.py example.txt                    # writes party_crawl.gif
python3 textcrawl.py mytext.txt -o session12.gif    # pick the output name
python3 textcrawl.py mytext.txt --frames 900        # more frames = slower crawl
python3 textcrawl.py mytext.txt --debug             # step-by-step diagnostics
```

| Option | Default | What it does |
|---|---|---|
| `text_file` | (required) | UTF-8 text file with the crawl text |
| `-o`, `--output` | `party_crawl.gif` | Output GIF |
| `--frames` | `640` | Number of frames (controls crawl speed) |
| `--fps` | `24` | Frames per second |
| `--font-size` | `34` | Font size in pixels |
| `--debug` | off | Prints what each step is doing, to stderr |
| `--selftest` | — | Runs the built-in tests and exits |

### Text file format

- Each line in the file starts a new line in the crawl.
- A blank line makes a paragraph gap.
- Long lines are word-wrapped automatically, so you can write one paragraph
  per line.
- Save as UTF-8 so curly quotes and `…` render properly. Windows line endings
  and a BOM are handled.

If your text is long, the script will suggest a `--frames` value so it doesn't
scroll by at hyperspace speed.

## Self-test

```bash
python3 textcrawl.py --selftest
```

Expected output ends with:

```
Self-test passed (8 checks).
```

It works on throwaway text in a temporary folder and leaves nothing behind.
(One `WARNING: word too wide` line is expected — that's one of the tests.)

## Files

| File | Purpose |
|---|---|
| `textcrawl.py` | The script |
| `example.txt` | Sample crawl text |
| `demo.gif` | Preview shown above |
| `requirements.txt` | Python dependencies (Pillow, numpy) |

## Disclaimer

A fan-made tool for fun. Not affiliated with or endorsed by Lucasfilm or
Disney. Star Wars is a trademark of Lucasfilm Ltd.

## License

MIT — see [LICENSE](LICENSE).
