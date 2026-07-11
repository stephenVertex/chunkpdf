#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pymupdf>=1.24",
#     "pillow>=10.0",
# ]
# ///
"""
chunkpdf - Convert a PDF into one PNG per page at a low resolution,
or into an animated GIF carousel of all pages.

Intended for feeding pages to LLMs for layout evaluation, where small,
low-quality images are sufficient and keep token/byte counts down, or for
sharing page carousels on platforms that don't accept PDFs directly.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pymupdf  # PyMuPDF
from PIL import Image

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMG]?)B?\s*$", re.IGNORECASE)
_SIZE_UNITS = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}
_MIN_PX = 64


def parse_size(text: str) -> int:
    """Parse a human-readable byte size (e.g. ``500KB``, ``1.5MB``, ``500000``).

    Returns the size in bytes as an int.  Raises ``ValueError`` on bad input.
    """
    m = _SIZE_RE.match(text)
    if not m:
        raise ValueError(
            f"Invalid size {text!r} — expected e.g. 500KB, 1.5MB, 2GB, or a raw byte count"
        )
    value = float(m.group(1))
    unit = m.group(2).upper()
    result = int(value * _SIZE_UNITS[unit])
    if result <= 0:
        raise ValueError(f"Size must be positive, got {result}")
    return result


def _render_pixmap(
    page: pymupdf.Page, zoom: float, max_width: int | None
) -> pymupdf.Pixmap:
    """Render *page* at *zoom* honouring the *max_width* pixel cap."""
    matrix = pymupdf.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    if max_width and pix.width > max_width:
        scale = max_width / pix.width
        matrix = pymupdf.Matrix(zoom * scale, zoom * scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
    return pix


def _fit_size_budget(
    page: pymupdf.Page,
    base_zoom: float,
    max_width: int | None,
    max_size: int,
) -> pymupdf.Pixmap:
    """Render *page* and iteratively reduce quality until the PNG fits *max_size* bytes.

    The initial render uses *base_zoom* and *max_width* as usual.  If the
    resulting PNG exceeds *max_size*, the zoom is reduced in steps until the
    PNG fits or the image reaches ``_MIN_PX`` pixels wide (whichever comes
    first).  A warning is printed to stderr if the budget cannot be met.
    """
    pix = _render_pixmap(page, base_zoom, max_width)
    data = pix.tobytes("png")
    if len(data) <= max_size:
        return pix

    zoom = base_zoom
    while pix.width > _MIN_PX:
        # Estimate the zoom reduction needed from the byte-size ratio, with a
        # 0.9 safety margin so we converge in few iterations.
        ratio = max_size / len(data)
        zoom *= ratio**0.5 * 0.9
        pix = _render_pixmap(page, zoom, max_width)
        data = pix.tobytes("png")
        if len(data) <= max_size:
            return pix

    print(
        f"Warning: could not fit page under {max_size} bytes "
        f"(best: {len(data)} at {pix.width}x{pix.height})",
        file=sys.stderr,
    )
    return pix


def _pixmap_to_pil(pix: pymupdf.Pixmap) -> Image.Image:
    """Convert a PyMuPDF RGB Pixmap to a Pillow Image."""
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def render_pdf_pages(
    input_path: Path,
    dpi: int = 72,
    max_width: int | None = 1024,
) -> list[Image.Image]:
    """Render each page of a PDF to a PIL RGB Image."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    doc = pymupdf.open(input_path)
    images: list[Image.Image] = []
    base_zoom = dpi / 72.0
    for page in doc:
        pix = _render_pixmap(page, base_zoom, max_width)
        images.append(_pixmap_to_pil(pix))
    doc.close()
    return images


def generate_turn_frames(
    current: Image.Image,
    next_page: Image.Image,
    fps: int = 15,
    duration: float = 0.5,
) -> list[Image.Image]:
    """Generate slide-transition frames between two pages.

    The current page slides out to the left while the next page slides in
    from the right, creating a page-turn effect.
    """
    width, height = current.size
    if next_page.size != current.size:
        next_page = next_page.resize(current.size)

    num_frames = max(1, int(fps * duration))
    frames: list[Image.Image] = []

    for i in range(1, num_frames + 1):
        progress = i / num_frames
        offset = int(width * progress)
        frame = Image.new("RGB", (width, height), (255, 255, 255))
        if offset < width:
            frame.paste(current, (-offset, 0))
            frame.paste(next_page, (width - offset, 0))
        else:
            frame.paste(next_page, (0, 0))
        frames.append(frame)

    return frames


def convert_pdf_to_gif(
    input_path: Path,
    output_path: Path | None = None,
    dpi: int = 72,
    max_width: int | None = 1024,
    seconds_per_page: float = 2.0,
    page_turn: bool = False,
    turn_fps: int = 15,
    turn_duration: float = 0.5,
) -> Path:
    """Convert a PDF to an animated GIF carousel.

    Each page is displayed for *seconds_per_page* seconds.  When
    *page_turn* is True a slide transition is inserted between
    consecutive pages.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}.gif"

    images = render_pdf_pages(input_path, dpi=dpi, max_width=max_width)
    if not images:
        raise ValueError("PDF has no pages")

    # Normalise all pages to the first page's dimensions (GIF needs
    # uniform frame size).
    ref_size = images[0].size
    images = [
        img if img.size == ref_size else img.resize(ref_size)
        for img in images
    ]

    page_duration_ms = int(seconds_per_page * 1000)
    turn_frame_ms = int(1000 / turn_fps) if turn_fps > 0 else 67

    frames: list[Image.Image] = []
    durations: list[int] = []

    for i, img in enumerate(images):
        frames.append(img)
        durations.append(page_duration_ms)

        if page_turn and i < len(images) - 1:
            transition = generate_turn_frames(
                img, images[i + 1],
                fps=turn_fps, duration=turn_duration,
            )
            for tf in transition:
                frames.append(tf)
                durations.append(turn_frame_ms)

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )

    print(
        f"Wrote {output_path}  "
        f"({len(images)} pages, {len(frames)} frames)"
    )
    return output_path


def convert_pdf_to_pngs(
    input_path: Path,
    output_dir: Path | None = None,
    dpi: int = 72,
    max_width: int | None = 1024,
    max_size: int | None = None,
) -> list[Path]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if output_dir is None:
        output_dir = input_path.parent / f"{input_path.stem}_pages"
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(input_path)
    total = doc.page_count
    pad = len(str(total))
    written: list[Path] = []
    base_zoom = dpi / 72.0

    for i, page in enumerate(doc, start=1):
        if max_size is not None:
            pix = _fit_size_budget(page, base_zoom, max_width, max_size)
        else:
            pix = _render_pixmap(page, base_zoom, max_width)

        out = output_dir / f"{input_path.stem}_p{str(i).zfill(pad)}.png"
        pix.save(out)
        written.append(out)
        size_str = f", {out.stat().st_size} bytes" if max_size is not None else ""
        print(f"Wrote {out}  ({pix.width}x{pix.height}{size_str})")

    doc.close()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a PDF to one low-quality PNG per page (for LLM layout review), "
        "or to an animated GIF carousel."
    )
    parser.add_argument("input_pdf", type=Path, help="Path to input PDF")
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=None,
        help="Output directory for PNGs (default: <pdf_stem>_pages next to input). "
        "In GIF mode (--gif), this is the output .gif file path.",
    )
    parser.add_argument(
        "-d", "--dpi", type=int, default=72,
        help="Rendering DPI (default: 72 — low quality, good for LLMs)",
    )
    parser.add_argument(
        "-w", "--max-width", type=int, default=1024,
        help="Max pixel width; pages are scaled down to fit (default: 1024). Use 0 to disable.",
    )
    parser.add_argument(
        "-s", "--max-size", type=str, default=None,
        help=(
            "Max file size per output PNG (e.g. 500KB, 1.5MB). "
            "Pages are iteratively downscaled until each PNG fits. "
            "Use 0 to disable."
        ),
    )
    parser.add_argument(
        "--gif", action="store_true",
        help="Output an animated GIF carousel instead of individual PNGs.",
    )
    parser.add_argument(
        "--seconds-per-page", type=float, default=2.0, metavar="SECONDS",
        help="Seconds each page is displayed in the GIF (default: 2.0).",
    )
    parser.add_argument(
        "--page-turn", action="store_true",
        help="Add a slide page-turn transition between pages in the GIF.",
    )
    parser.add_argument(
        "--turn-fps", type=int, default=15,
        help="Frame rate for page-turn transitions (default: 15).",
    )
    parser.add_argument(
        "--turn-duration", type=float, default=0.5, metavar="SECONDS",
        help="Duration of each page-turn transition in seconds (default: 0.5).",
    )
    args = parser.parse_args()

    max_width = args.max_width if args.max_width and args.max_width > 0 else None

    max_size: int | None = None
    if args.max_size and args.max_size != "0":
        try:
            max_size = parse_size(args.max_size)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    try:
        if args.gif:
            convert_pdf_to_gif(
                input_path=args.input_pdf,
                output_path=args.output_dir,
                dpi=args.dpi,
                max_width=max_width,
                seconds_per_page=args.seconds_per_page,
                page_turn=args.page_turn,
                turn_fps=args.turn_fps,
                turn_duration=args.turn_duration,
            )
        else:
            convert_pdf_to_pngs(
                input_path=args.input_pdf,
                output_dir=args.output_dir,
                dpi=args.dpi,
                max_width=max_width,
                max_size=max_size,
            )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
