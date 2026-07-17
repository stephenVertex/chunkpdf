# chunkpdf

Convert a PDF into one low-quality PNG per page, or into an animated GIF
carousel of all pages — intended for feeding pages to LLMs for layout
evaluation, or for sharing on platforms that don't support PDF carousels
directly.

## Install

Requires [`uv`](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:stephenVertex/chunkpdf.git
cd chunkpdf
uv tool install --editable .
```

This installs the `chunkpdf` command globally (editable, so updates to the
repo are picked up automatically). Dependencies (PyMuPDF, Pillow, Python
3.13+) are managed by `uv`.

To verify:

```bash
chunkpdf --version
```

## Usage

```bash
chunkpdf document.pdf                  # -> document_pages/document_p01.png, ...
chunkpdf document.pdf -o ./out         # custom output directory
chunkpdf document.pdf -d 96            # render at 96 DPI (default: 72)
chunkpdf document.pdf -w 800           # cap width at 800px (default: 1024)
chunkpdf document.pdf -w 0             # disable width cap
chunkpdf document.pdf -s 500KB         # cap each PNG at 500 KB
chunkpdf document.pdf -d 300 -s 1MB    # high DPI, but keep each PNG under 1 MB
```

### Animated GIF carousel

```bash
chunkpdf document.pdf --gif                      # -> document.gif (2s per page)
chunkpdf document.pdf --gif -o ./slideshow.gif   # custom output path
chunkpdf document.pdf --gif --seconds-per-page 5 # each page shown for 5s
chunkpdf document.pdf --gif --page-turn          # slide transition between pages
chunkpdf document.pdf --gif --page-turn --turn-fps 24 --turn-duration 0.8
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--version` | — | Show version number and exit |
| `-o`, `--output-dir` | `<stem>_pages` next to input | Output directory (PNG mode) or `.gif` file (GIF mode) |
| `-d`, `--dpi` | `72` | Rendering DPI |
| `-w`, `--max-width` | `1024` | Max pixel width; pages scaled down to fit. `0` to disable. |
| `-s`, `--max-size` | _none_ | Max file size per output PNG (e.g. `500KB`, `1.5MB`). Pages are iteratively downscaled until each PNG fits. `0` to disable. |
| `--gif` | off | Output an animated GIF carousel instead of individual PNGs |
| `--seconds-per-page` | `2.0` | Seconds each page is displayed in the GIF |
| `--page-turn` | off | Add a slide page-turn transition between pages in the GIF |
| `--turn-fps` | `15` | Frame rate for page-turn transitions |
| `--turn-duration` | `0.5` | Duration of each page-turn transition in seconds |

## Why

PDFs shipped to an LLM for layout critique don't need print-quality renders.
72 DPI, capped at 1024px wide, produces legible page thumbnails that are cheap
to transfer and evaluate.

### Size-capped output

Some contexts (GitHub READMEs, Discord messages, API uploads) impose a
per-file size limit. Use `--max-size` to guarantee each PNG stays under a
budget. chunkpdf renders the page at the requested DPI/width, then iteratively
downscales until the PNG fits:

```bash
chunkpdf report.pdf -s 500KB    # every page PNG ≤ 500 KB
```

The GIF carousel mode is useful when you need to share a multi-page PDF on
platforms that only accept images (e.g. social media, chat apps). The
`--page-turn` option adds a smooth slide transition between pages, making the
carousel feel like a native slideshow.
