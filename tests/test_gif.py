"""Tests for the GIF conversion feature of chunkpdf."""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PIL import Image

import chunkpdf


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a small 3-page PDF for testing."""
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page(width=400, height=300)
        page.insert_text((50, 50), f"Page {i+1}", fontsize=48, color=(0, 0, 1))
        page.draw_rect(pymupdf.Rect(20, 20, 380, 280), color=(1, 0, 0), width=2)
    pdf_path = tmp_path / "sample.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def single_page_pdf(tmp_path: Path) -> Path:
    """Create a single-page PDF."""
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=150)
    page.insert_text((20, 30), "Solo", fontsize=24)
    pdf_path = tmp_path / "single.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def empty_pdf(tmp_path: Path) -> Path:
    """Create an empty PDF (zero pages) via raw bytes."""
    pdf = b"%PDF-1.0\n"
    off1 = len(pdf)
    pdf += b"1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n"
    off2 = len(pdf)
    pdf += b"2 0 obj\n<</Type/Pages/Count 0/Kids[]>>\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 3\n"
    pdf += b"0000000000 65535 f \n"
    pdf += f"{off1:010d} 00000 n \n".encode()
    pdf += f"{off2:010d} 00000 n \n".encode()
    pdf += b"trailer\n<</Size 3/Root 1 0 R>>\n"
    pdf += b"startxref\n"
    pdf += f"{xref}\n".encode()
    pdf += b"%%EOF\n"
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(pdf)
    return pdf_path


# ---------------------------------------------------------------------------
# render_pdf_pages
# ---------------------------------------------------------------------------

class TestRenderPdfPages:
    def test_returns_pil_images(self, sample_pdf: Path):
        images = chunkpdf.render_pdf_pages(sample_pdf)
        assert len(images) == 3
        for img in images:
            assert isinstance(img, Image.Image)
            assert img.mode == "RGB"

    def test_respects_max_width(self, sample_pdf: Path):
        images = chunkpdf.render_pdf_pages(sample_pdf, max_width=100)
        for img in images:
            assert img.width <= 100

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            chunkpdf.render_pdf_pages(Path("/nonexistent/file.pdf"))


# ---------------------------------------------------------------------------
# convert_pdf_to_gif — basic (no page-turn)
# ---------------------------------------------------------------------------

class TestConvertPdfToGifBasic:
    def test_creates_gif_file(self, sample_pdf: Path, tmp_path: Path):
        out = tmp_path / "output.gif"
        result = chunkpdf.convert_pdf_to_gif(sample_pdf, output_path=out)
        assert result == out
        assert out.exists()

    def test_default_output_path(self, sample_pdf: Path):
        result = chunkpdf.convert_pdf_to_gif(sample_pdf)
        expected = sample_pdf.parent / f"{sample_pdf.stem}.gif"
        assert result == expected
        assert expected.exists()
        expected.unlink()

    def test_frame_count_no_turn(self, sample_pdf: Path, tmp_path: Path):
        out = tmp_path / "output.gif"
        chunkpdf.convert_pdf_to_gif(sample_pdf, output_path=out)
        img = Image.open(out)
        assert img.n_frames == 3

    def test_frame_durations(self, sample_pdf: Path, tmp_path: Path):
        out = tmp_path / "output.gif"
        chunkpdf.convert_pdf_to_gif(
            sample_pdf, output_path=out, seconds_per_page=3.0,
        )
        img = Image.open(out)
        for i in range(img.n_frames):
            img.seek(i)
            assert img.info["duration"] == 3000

    def test_single_page(self, single_page_pdf: Path, tmp_path: Path):
        out = tmp_path / "single.gif"
        chunkpdf.convert_pdf_to_gif(single_page_pdf, output_path=out)
        img = Image.open(out)
        assert img.n_frames == 1

    def test_empty_pdf_raises(self, empty_pdf: Path, tmp_path: Path):
        out = tmp_path / "empty.gif"
        with pytest.raises(ValueError, match="no pages"):
            chunkpdf.convert_pdf_to_gif(empty_pdf, output_path=out)

    def test_missing_file_raises(self, tmp_path: Path):
        out = tmp_path / "nope.gif"
        with pytest.raises(FileNotFoundError):
            chunkpdf.convert_pdf_to_gif(Path("/nonexistent.pdf"), output_path=out)


# ---------------------------------------------------------------------------
# convert_pdf_to_gif — with page-turn
# ---------------------------------------------------------------------------

class TestConvertPdfToGifPageTurn:
    def test_more_frames_with_turn(self, sample_pdf: Path, tmp_path: Path):
        out_basic = tmp_path / "basic.gif"
        out_turn = tmp_path / "turn.gif"
        chunkpdf.convert_pdf_to_gif(sample_pdf, output_path=out_basic)
        chunkpdf.convert_pdf_to_gif(
            sample_pdf, output_path=out_turn, page_turn=True,
        )
        basic = Image.open(out_basic)
        turn = Image.open(out_turn)
        assert turn.n_frames > basic.n_frames

    def test_turn_frame_count(self, sample_pdf: Path, tmp_path: Path):
        out = tmp_path / "turn.gif"
        chunkpdf.convert_pdf_to_gif(
            sample_pdf, output_path=out,
            page_turn=True, turn_fps=15, turn_duration=0.5,
        )
        img = Image.open(out)
        # 3 page frames + 2 transitions (7 frames each, last may be
        # optimised away by PIL) → at least 3 + 2*6 = 15.
        assert img.n_frames >= 15

    def test_custom_turn_settings(self, sample_pdf: Path, tmp_path: Path):
        out = tmp_path / "custom.gif"
        chunkpdf.convert_pdf_to_gif(
            sample_pdf, output_path=out,
            page_turn=True, turn_fps=10, turn_duration=1.0,
        )
        img = Image.open(out)
        # 3 + 2*(10-1) = 21 minimum after optimisation.
        assert img.n_frames >= 21

    def test_turn_transition_durations(self, sample_pdf: Path, tmp_path: Path):
        out = tmp_path / "turn.gif"
        chunkpdf.convert_pdf_to_gif(
            sample_pdf, output_path=out,
            page_turn=True, turn_fps=15, turn_duration=0.5,
            seconds_per_page=2.0,
        )
        img = Image.open(out)
        img.seek(0)
        assert img.info["duration"] == 2000
        img.seek(1)
        assert img.info["duration"] < 2000

    def test_single_page_no_turn_frames(
        self, single_page_pdf: Path, tmp_path: Path,
    ):
        out = tmp_path / "single_turn.gif"
        chunkpdf.convert_pdf_to_gif(
            single_page_pdf, output_path=out, page_turn=True,
        )
        img = Image.open(out)
        assert img.n_frames == 1


# ---------------------------------------------------------------------------
# generate_turn_frames
# ---------------------------------------------------------------------------

class TestGenerateTurnFrames:
    def test_frame_count(self):
        current = Image.new("RGB", (100, 50), (255, 0, 0))
        nxt = Image.new("RGB", (100, 50), (0, 255, 0))
        frames = chunkpdf.generate_turn_frames(
            current, nxt, fps=10, duration=1.0,
        )
        assert len(frames) == 10

    def test_first_frame_is_partial(self):
        current = Image.new("RGB", (100, 50), (255, 0, 0))
        nxt = Image.new("RGB", (100, 50), (0, 255, 0))
        frames = chunkpdf.generate_turn_frames(
            current, nxt, fps=10, duration=1.0,
        )
        frame = frames[0]
        # progress=0.1 → offset=10 → current slides left, next slides in from right
        # x=5 is in current page area (red), x=95 is in next page area (green)
        assert frame.getpixel((5, 25)) == (255, 0, 0)
        assert frame.getpixel((95, 25)) == (0, 255, 0)

    def test_last_frame_is_next_page(self):
        current = Image.new("RGB", (100, 50), (255, 0, 0))
        nxt = Image.new("RGB", (100, 50), (0, 255, 0))
        frames = chunkpdf.generate_turn_frames(
            current, nxt, fps=10, duration=1.0,
        )
        frame = frames[-1]
        assert frame.getpixel((50, 25)) == (0, 255, 0)

    def test_different_sizes_resized(self):
        current = Image.new("RGB", (100, 50), (255, 0, 0))
        nxt = Image.new("RGB", (200, 100), (0, 255, 0))
        frames = chunkpdf.generate_turn_frames(
            current, nxt, fps=5, duration=0.5,
        )
        for frame in frames:
            assert frame.size == (100, 50)

    def test_min_one_frame(self):
        current = Image.new("RGB", (100, 50), (255, 0, 0))
        nxt = Image.new("RGB", (100, 50), (0, 255, 0))
        frames = chunkpdf.generate_turn_frames(
            current, nxt, fps=1, duration=0.1,
        )
        assert len(frames) >= 1
