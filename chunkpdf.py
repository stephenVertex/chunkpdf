#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pymupdf>=1.24",
# ]
# ///
"""
chunkpdf - Convert a PDF into one PNG per page at a low resolution.

Intended for feeding pages to LLMs for layout evaluation, where small,
low-quality images are sufficient and keep token/byte counts down.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pymupdf  # PyMuPDF

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
        description="Convert a PDF to one low-quality PNG per page (for LLM layout review)."
    )
    parser.add_argument("input_pdf", type=Path, help="Path to input PDF")
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=None,
        help="Output directory (default: <pdf_stem>_pages next to input)",
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
