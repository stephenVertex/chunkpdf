# chunkpdf

Convert a PDF into one low-quality PNG per page — intended for feeding pages to
LLMs for layout evaluation, where small images keep token/byte counts down.

## Install

```bash
git clone git@github.com:stephenVertex/chunkpdf.git
cd chunkpdf
./install.sh
```

This symlinks `chunkpdf.py` into `~/.local/bin/chunkpdf`. Make sure
`~/.local/bin` is on your `PATH`.

Requires [`uv`](https://docs.astral.sh/uv/). Dependencies (PyMuPDF, Python
3.13+) are resolved automatically by the uv script shebang on first run.

## Usage

```bash
chunkpdf document.pdf                  # -> document_pages/document_p01.png, ...
chunkpdf document.pdf -o ./out         # custom output directory
chunkpdf document.pdf -d 96            # render at 96 DPI (default: 72)
chunkpdf document.pdf -w 800           # cap width at 800px (default: 1024)
chunkpdf document.pdf -w 0             # disable width cap
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `-o`, `--output-dir` | `<stem>_pages` next to input | Where PNGs are written |
| `-d`, `--dpi` | `72` | Rendering DPI |
| `-w`, `--max-width` | `1024` | Max pixel width; pages scaled down to fit. `0` to disable. |

## Why

PDFs shipped to an LLM for layout critique don't need print-quality renders.
72 DPI, capped at 1024px wide, produces legible page thumbnails that are cheap
to transfer and evaluate.
