"""
chunkpdf - Convert a PDF into one PNG per page at a low resolution.

Intended for feeding pages to LLMs for layout evaluation, where small,
low-quality images are sufficient and keep token/byte counts down.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf  # PyMuPDF


def convert_pdf_to_pngs(
    input_path: Path,
    output_dir: Path | None = None,
    dpi: int = 72,
    max_width: int | None = 1024,
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

    for i, page in enumerate(doc, start=1):
        # Base matrix from DPI
        zoom = dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        # Downscale further if wider than max_width
        if max_width and pix.width > max_width:
            scale = max_width / pix.width
            matrix = pymupdf.Matrix(zoom * scale, zoom * scale)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

        out = output_dir / f"{input_path.stem}_p{str(i).zfill(pad)}.png"
        pix.save(out)
        written.append(out)
        print(f"Wrote {out}  ({pix.width}x{pix.height})")

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
    args = parser.parse_args()

    max_width = args.max_width if args.max_width and args.max_width > 0 else None

    try:
        convert_pdf_to_pngs(
            input_path=args.input_pdf,
            output_dir=args.output_dir,
            dpi=args.dpi,
            max_width=max_width,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
