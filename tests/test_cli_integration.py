"""Integration tests verifying GIF and max-size features coexist in the CLI.

These tests validate the rework goal: after rebasing the GIF carousel feature
onto main (which added ``--max-size``, ``--version``, and the packaged
``src/`` install layout), both feature sets remain available and functional
through the same command-line interface.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest
from PIL import Image


@pytest.fixture
def cli_pdf(tmp_path: Path) -> Path:
    """Create a small 2-page PDF for CLI integration tests."""
    doc = pymupdf.open()
    for i in range(2):
        page = doc.new_page(width=400, height=300)
        page.insert_text((50, 50), f"Page {i + 1}", fontsize=48)
    pdf_path = tmp_path / "cli_sample.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _run_chunkpdf(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "chunkpdf", *args],
        capture_output=True,
        text=True,
    )


class TestCliExposesBothFeatures:
    """The CLI must expose flags from both the GIF and max-size features."""

    def test_help_lists_gif_flags(self):
        result = _run_chunkpdf("--help")
        assert result.returncode == 0, result.stderr
        for flag in (
            "--gif",
            "--seconds-per-page",
            "--page-turn",
            "--turn-fps",
            "--turn-duration",
        ):
            assert flag in result.stdout, f"{flag} missing from --help"

    def test_help_lists_max_size_and_install_flags(self):
        result = _run_chunkpdf("--help")
        assert result.returncode == 0, result.stderr
        for flag in ("--max-size", "--version", "--max-width", "--dpi"):
            assert flag in result.stdout, f"{flag} missing from --help"

    def test_version_flag_works(self):
        result = _run_chunkpdf("--version")
        assert result.returncode == 0, result.stderr
        assert "chunkpdf" in result.stdout


class TestCliEndToEnd:
    """Both features must produce correct output when invoked via the CLI."""

    def test_cli_gif_mode(self, cli_pdf: Path, tmp_path: Path):
        out = tmp_path / "cli_out.gif"
        result = _run_chunkpdf(str(cli_pdf), "--gif", "-o", str(out))
        assert result.returncode == 0, result.stderr
        assert out.exists()
        img = Image.open(out)
        assert img.n_frames == 2

    def test_cli_gif_with_page_turn(self, cli_pdf: Path, tmp_path: Path):
        out = tmp_path / "cli_turn.gif"
        result = _run_chunkpdf(
            str(cli_pdf), "--gif", "--page-turn", "-o", str(out),
        )
        assert result.returncode == 0, result.stderr
        assert out.exists()
        img = Image.open(out)
        # 2 page frames + 1 transition (at least 6 frames) → > 2
        assert img.n_frames > 2

    def test_cli_max_size_mode(self, cli_pdf: Path, tmp_path: Path):
        out_dir = tmp_path / "cli_pages"
        result = _run_chunkpdf(
            str(cli_pdf), "-o", str(out_dir), "-s", "10KB",
        )
        assert result.returncode == 0, result.stderr
        files = sorted(out_dir.glob("*.png"))
        assert len(files) == 2
        for f in files:
            assert f.stat().st_size <= 10_000

    def test_cli_png_default_mode(self, cli_pdf: Path, tmp_path: Path):
        out_dir = tmp_path / "cli_default_pages"
        result = _run_chunkpdf(str(cli_pdf), "-o", str(out_dir))
        assert result.returncode == 0, result.stderr
        files = sorted(out_dir.glob("*.png"))
        assert len(files) == 2
