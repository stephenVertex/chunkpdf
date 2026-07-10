"""Tests for the --max-size file-size capping feature."""

from __future__ import annotations

import importlib
from pathlib import Path

import pymupdf
import pytest

chunkpdf = importlib.import_module("chunkpdf")
parse_size = chunkpdf.parse_size
convert_pdf_to_pngs = chunkpdf.convert_pdf_to_pngs


# ---------------------------------------------------------------------------
# parse_size
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("500", 500),
        ("500B", 500),
        ("500b", 500),
        ("1KB", 1024),
        ("1kb", 1024),
        ("1K", 1024),
        ("500KB", 500 * 1024),
        ("1.5MB", int(1.5 * 1024**2)),
        ("2MB", 2 * 1024**2),
        ("1GB", 1024**3),
        ("  100 KB  ", 100 * 1024),
        ("0.5K", 512),
    ],
)
def test_parse_size_valid(text: str, expected: int) -> None:
    assert parse_size(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "KB", "-5KB", "1.2.3KB", "5XB"])
def test_parse_size_invalid(text: str) -> None:
    with pytest.raises(ValueError):
        parse_size(text)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def text_pdf(tmp_path: Path) -> Path:
    """Create a multi-page PDF with enough detail to produce sizable PNGs."""
    doc = pymupdf.open()
    for p in range(3):
        page = doc.new_page(width=612, height=792)
        for y in range(50, 750, 18):
            page.insert_text(
                (50, y),
                f"Page {p+1} line {y}: The quick brown fox jumps. "
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
                fontsize=10,
            )
        for i in range(8):
            page.draw_rect(
                pymupdf.Rect(50 + i * 8, 50 + i * 8, 200 + i * 8, 200 + i * 8),
                color=(1, 0, 0),
                width=0.5,
            )
    out = tmp_path / "test.pdf"
    doc.save(str(out))
    doc.close()
    return out


# ---------------------------------------------------------------------------
# convert_pdf_to_pngs with max_size
# ---------------------------------------------------------------------------

def test_no_max_size_unchanged(text_pdf: Path, tmp_path: Path) -> None:
    """Without max_size the output should be the same as the default render."""
    out_dir = tmp_path / "out_default"
    files = convert_pdf_to_pngs(text_pdf, output_dir=out_dir)
    assert len(files) == 3
    for f in files:
        assert f.exists()
        assert f.suffix == ".png"


def test_max_size_caps_each_page(text_pdf: Path, tmp_path: Path) -> None:
    """Every output PNG must be at or under the max_size budget."""
    budget = 20_000  # 20 KB — smaller than the default render
    out_dir = tmp_path / "out_capped"
    files = convert_pdf_to_pngs(
        text_pdf, output_dir=out_dir, max_size=budget
    )
    assert len(files) == 3
    for f in files:
        assert f.exists()
        size = f.stat().st_size
        assert size <= budget, f"{f.name} is {size} bytes, exceeds {budget}"


def test_max_size_no_op_when_already_under(text_pdf: Path, tmp_path: Path) -> None:
    """If the default render already fits, dimensions should be unchanged."""
    big_budget = 500 * 1024 * 1024  # 500 MB — always larger
    out_default = tmp_path / "default"
    out_big = tmp_path / "big"
    files_default = convert_pdf_to_pngs(text_pdf, output_dir=out_default)
    files_big = convert_pdf_to_pngs(
        text_pdf, output_dir=out_big, max_size=big_budget
    )
    for fd, fb in zip(files_default, files_big):
        assert fd.stat().st_size == fb.stat().st_size


def test_max_size_with_high_dpi(text_pdf: Path, tmp_path: Path) -> None:
    """High-DPI renders should still be capped to the byte budget."""
    budget = 15_000
    out_dir = tmp_path / "out_hdpi"
    files = convert_pdf_to_pngs(
        text_pdf, output_dir=out_dir, dpi=300, max_size=budget
    )
    for f in files:
        assert f.stat().st_size <= budget


def test_max_size_with_max_width(text_pdf: Path, tmp_path: Path) -> None:
    """max_width and max_size should compose correctly."""
    budget = 10_000
    out_dir = tmp_path / "out_mw"
    files = convert_pdf_to_pngs(
        text_pdf, output_dir=out_dir, max_width=800, max_size=budget
    )
    for f in files:
        assert f.stat().st_size <= budget
