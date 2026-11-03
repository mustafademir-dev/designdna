"""Aynı girdi -> birebir aynı çıktı."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import SNAPSHOTS_DIR
from designdna.cache import load_capture_file
from designdna.cli import app
from designdna.generators import OUTPUT_FILES

runner = CliRunner()
ALL_FILES = (*OUTPUT_FILES, "blend-report.json")


def _assert_identical(a: Path, b: Path) -> None:
    for name in ALL_FILES:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def _snap(name: str) -> str:
    return str(SNAPSHOTS_DIR / f"{name}.capture.json")


def test_blend_twice_identical(tmp_path: Path) -> None:
    outs = [tmp_path / "o1", tmp_path / "o2"]
    for out in outs:
        result = runner.invoke(
            app,
            ["blend", "--source", _snap("neo_brutalist") + "@0.5",
             "--source", _snap("linear_dark") + "@0.3",
             "--source", _snap("stripe_clean") + "@0.2", "-o", str(out)],
        )
        assert result.exit_code == 0, result.output
    _assert_identical(*outs)


def test_run_twice_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(url: str, *, browser=None):
        name = "stripe_clean" if "a.html" in url else "linear_dark"
        return load_capture_file(SNAPSHOTS_DIR / f"{name}.capture.json").model_copy(
            update={"source": url}
        )

    monkeypatch.setattr("designdna.extractor.dom_scanner.capture_source", fake)
    a = tmp_path / "a.html"
    b = tmp_path / "b.html"
    a.write_text("<html></html>", encoding="utf-8")
    b.write_text("<html></html>", encoding="utf-8")
    outs = [tmp_path / "o1", tmp_path / "o2"]
    for i, out in enumerate(outs):
        result = runner.invoke(
            app,
            ["run", "--source", f"{a}@0.6", "--source", f"{b}@0.4",
             "--cache-dir", str(tmp_path / f"c{i}"), "-o", str(out)],
        )
        assert result.exit_code == 0, result.output
    _assert_identical(*outs)
