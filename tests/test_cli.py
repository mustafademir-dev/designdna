"""CLI testleri (çoğu tarayıcısız)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import FIXTURES_DIR, SNAPSHOTS_DIR
from designdna.cache import CacheStore, load_capture_file
from designdna.cli import app
from designdna.generators import OUTPUT_FILES
from designdna.sources import parse_source

runner = CliRunner()

ALL_FILES = (*OUTPUT_FILES, "blend-report.json")


def _snap(name: str) -> str:
    return str(SNAPSHOTS_DIR / f"{name}.capture.json")


def _json_args(out: Path) -> list[str]:
    return [
        "blend",
        "--source", f"{_snap('neo_brutalist')}@0.5",
        "--source", f"{_snap('linear_dark')}@0.3",
        "--source", f"{_snap('stripe_clean')}@0.2",
        "--output", str(out),
    ]


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("extract", "blend", "run", "preview"):
        assert cmd in result.output


def test_blend_json_sources_writes_all_files(tmp_path: Path) -> None:
    out = tmp_path / "dist"
    result = runner.invoke(app, _json_args(out))
    assert result.exit_code == 0, result.output
    for name in ALL_FILES:
        assert (out / name).is_file(), name


def _fake_capture(name: str, location: str):
    return load_capture_file(SNAPSHOTS_DIR / f"{name}.capture.json").model_copy(
        update={"source": location}
    )


def test_blend_from_cache_without_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = tmp_path / "us@er" / "a.html"
    page.parent.mkdir()
    page.write_text("<html></html>", encoding="utf-8")
    spec = parse_source(str(page))
    cache = tmp_path / "cache"
    CacheStore(cache).save_capture(_fake_capture("stripe_clean", spec.location))

    def boom(*a, **k):
        raise AssertionError("tarayıcı açılmamalı")

    monkeypatch.setattr("designdna.extractor.dom_scanner.capture_source", boom)
    monkeypatch.setattr("playwright.sync_api.sync_playwright", boom)

    out = tmp_path / "dist"
    result = runner.invoke(
        app, ["blend", "--source", str(page), "--cache-dir", str(cache), "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    for name in ALL_FILES:
        assert (out / name).is_file()


def test_blend_missing_cache_fails(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["blend", "--source", "https://example.invalid", "--cache-dir", str(tmp_path / "c"),
         "-o", str(tmp_path / "dist")],
    )
    assert result.exit_code != 0
    assert "cache bulunamadı" in result.output
    assert "designdna extract" in result.output
    assert not (tmp_path / "dist").exists()


def test_invalid_weight_fails(tmp_path: Path) -> None:
    # '@0' pozitif ağırlık değildir (konumun parçası, spec §6); konumsuz ağırlık hata verir.
    result = runner.invoke(app, ["blend", "--source", "@0.5", "-o", str(tmp_path / "d")])
    assert result.exit_code != 0
    assert "Kaynak konumu eksik" in result.output


@pytest.mark.parametrize("cmd", ["extract", "blend", "run"])
def test_missing_source_turkish_error(cmd: str) -> None:
    result = runner.invoke(app, [cmd])
    assert result.exit_code != 0
    assert "En az bir --source verilmeli" in result.output
    assert "Missing option" not in result.output


def test_summary_uses_display_names(tmp_path: Path) -> None:
    result = runner.invoke(app, _json_args(tmp_path / "out"))
    assert result.exit_code == 0
    assert "file://" not in result.output
    assert "neo_brutalist" in result.output


def _patch_capture(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake(url: str, *, browser=None):
        calls.append(url)
        return _fake_capture("stripe_clean", url)

    monkeypatch.setattr("designdna.extractor.dom_scanner.capture_source", fake)
    return calls


def test_extract_uses_cache_and_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_capture(monkeypatch)
    page = tmp_path / "a.html"
    page.write_text("<html></html>", encoding="utf-8")
    cache = tmp_path / "cache"
    args = ["extract", "--source", str(page), "--cache-dir", str(cache)]

    r1 = runner.invoke(app, args)
    assert r1.exit_code == 0, r1.output
    assert len(calls) == 1 and "tarandı" in r1.output
    assert CacheStore(cache).has(parse_source(str(page)).location)

    r2 = runner.invoke(app, args)
    assert r2.exit_code == 0 and len(calls) == 1
    assert "cache'ten" in r2.output

    r3 = runner.invoke(app, [*args, "--refresh"])
    assert r3.exit_code == 0 and len(calls) == 2


def test_extract_missing_file_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_capture(monkeypatch)
    result = runner.invoke(
        app, ["extract", "--source", str(tmp_path / "yok.html"), "--cache-dir", str(tmp_path / "c")]
    )
    assert result.exit_code != 0
    assert "bulunamadı" in result.output
    assert calls == []


def test_extract_skips_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_capture(monkeypatch)
    result = runner.invoke(
        app, ["extract", "--source", _snap("stripe_clean"), "--cache-dir", str(tmp_path / "c")]
    )
    assert result.exit_code == 0 and calls == []
    assert "atlandı" in result.output


def test_run_extract_then_blend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_capture(monkeypatch)
    a = tmp_path / "a.html"
    a.write_text("<html></html>", encoding="utf-8")
    out = tmp_path / "dist"
    result = runner.invoke(
        app,
        ["run", "--source", f"{a}@0.7", "--source", _snap("linear_dark") + "@0.3",
         "--cache-dir", str(tmp_path / "c"), "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    for name in ALL_FILES:
        assert (out / name).is_file()


def test_preview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: opened.append(url) or True)
    (tmp_path / "preview.html").write_text("<html></html>", encoding="utf-8")
    result = runner.invoke(app, ["preview", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert opened == [(tmp_path / "preview.html").resolve().as_uri()]


def test_preview_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: opened.append(url) or True)
    result = runner.invoke(app, ["preview", str(tmp_path)])
    assert result.exit_code != 0
    assert "preview.html bulunamadı" in result.output
    assert opened == []


@pytest.mark.browser
def test_real_extract_and_blend(tmp_path: Path) -> None:
    page = FIXTURES_DIR / "neo_brutalist.html"
    cache = tmp_path / "cache"
    out = tmp_path / "dist"
    r1 = runner.invoke(app, ["extract", "--source", str(page), "--cache-dir", str(cache)])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(
        app, ["blend", "--source", f"{page}@1", "--cache-dir", str(cache), "-o", str(out)]
    )
    assert r2.exit_code == 0, r2.output
    for name in ALL_FILES:
        assert (out / name).is_file()
