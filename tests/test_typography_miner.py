"""typography_miner testleri (tarayıcısız)."""

from __future__ import annotations

from pathlib import Path

import pytest

from designdna.extractor.typography_miner import (
    TYPE_SCALE_RATIOS,
    is_monospace,
    mine_typography,
    primary_family,
)
from designdna.models import STYLE_PROPERTIES, BoundingBox, ElementRecord, FontFace, RawSnapshot, Viewport

FIXTURE = Path(__file__).parent / "fixtures" / "sample_snapshot.json"


def el(idx, tag, *, size="16px", family="Inter, sans-serif", weight="400", lh="normal", ls="normal",
       text=10, area=1000.0):
    styles = {k: "" for k in STYLE_PROPERTIES}
    styles.update({"font-size": size, "font-family": family, "font-weight": weight,
                   "line-height": lh, "letter-spacing": ls})
    return ElementRecord(
        idx=idx, parent_idx=None, depth=1, tag=tag, text_length=text,
        bbox=BoundingBox(x=0, y=0, width=10, height=10), area=area, in_viewport=True, styles=styles,
    )


def snap(elements, **kw):
    return RawSnapshot(
        tool_version="0.1.0", source="file:///t.html", viewport=Viewport(name="desktop", width=1440, height=900),
        color_scheme="light", natural_mode="light", dominant_background="#ffffff", page_height=900.0,
        elements=elements, **kw,
    )


def test_primary_family():
    assert primary_family('"Helvetica Neue", Arial, sans-serif') == "Helvetica Neue"
    assert primary_family("'Inter', sans-serif") == "Inter"
    assert primary_family("monospace") == "monospace"
    assert primary_family("ui-sans-serif, system-ui") == "ui-sans-serif"
    assert primary_family('"A, B", serif') == "A, B"
    assert primary_family("") == ""


@pytest.mark.parametrize(
    "stack,expected",
    [
        ('"JetBrains Mono", monospace', True),
        ("Courier New, monospace", True),
        ("SFMono-Regular, Menlo, monospace", True),
        ("Fira Code", True),
        ("Berkeley Typeface, monospace", True),
        ("Inter, monospace", False),
        ("Inter, sans-serif", False),
        ("Georgia, serif", False),
        ("ui-monospace, SFMono-Regular", True),
    ],
)
def test_is_monospace(stack, expected):
    assert is_monospace(stack) is expected


def test_scale_ratio_snaps_to_125():
    sizes = {"p": 16, "h4": 20, "h3": 25, "h2": 31.25, "h1": 39.0625}
    t = mine_typography(snap([el(i, tag, size=f"{s}px") for i, (tag, s) in enumerate(sizes.items())]))
    assert abs(t.measured_ratio - 1.25) < 1e-3
    assert t.scale_ratio == 1.25
    assert t.base_size_px == 16


def test_scale_ratio_snaps_to_nearest_and_default():
    t = mine_typography(snap([el(0, "p", size="16px"), el(1, "h1", size="64px")]))  # 4 adım: 64/16=4 -> 1.414
    assert t.scale_ratio == 1.414
    assert t.measured_ratio == pytest.approx(1.4142, abs=1e-3)
    t = mine_typography(snap([el(0, "p")]))
    assert t.measured_ratio == 1.25 and t.scale_ratio == 1.25
    assert all(r in TYPE_SCALE_RATIOS for r in (t.scale_ratio,))


def test_headings_not_above_base_skipped():
    t = mine_typography(snap([el(0, "p", size="16px"), el(1, "h5", size="14px"), el(2, "h4", size="24px")]))
    assert t.measured_ratio == 1.5 and t.scale_ratio == 1.5


def test_line_height_and_letter_spacing_conversion():
    t = mine_typography(snap([
        el(0, "p", size="16px", lh="24px", ls="0.32px"),
        el(1, "h1", size="40px", lh="normal", ls="-0.8px"),
        el(2, "h2", size="20px", lh="1.3", ls="0.05em"),
        el(3, "small", size="12px", lh="150%", ls="normal"),
    ]))
    assert t.styles["p"].line_height == 1.5 and t.styles["p"].letter_spacing_em == pytest.approx(0.02)
    assert t.styles["h1"].line_height == 1.2 and t.styles["h1"].letter_spacing_em == pytest.approx(-0.02)
    assert t.styles["h2"].line_height == 1.3 and t.styles["h2"].letter_spacing_em == pytest.approx(0.05)
    assert t.styles["small"].line_height == 1.5 and t.styles["small"].letter_spacing_em == 0


def test_style_mode_is_area_weighted_and_tie_deterministic():
    t = mine_typography(snap([
        el(0, "p", size="16px", weight="400", area=100),
        el(1, "p", size="16px", weight="500", area=300),
        el(2, "p", size="18px", weight="500", area=150),
    ]))
    s = t.styles["p"]
    assert s.font_size_px == 16 and s.font_weight == 500 and s.samples == 3
    t = mine_typography(snap([el(0, "p", size="18px", area=100), el(1, "p", size="16px", area=100)]))
    assert t.styles["p"].font_size_px == 16  # eşitlikte sıralamaya göre


def test_weight_keywords_and_zero_text_not_dropped():
    t = mine_typography(snap([el(0, "h1", weight="bold", text=0), el(1, "button", weight="normal", text=0)]))
    assert t.styles["h1"].font_weight == 700 and t.styles["button"].font_weight == 400
    assert "h2" not in t.styles


def test_font_roles_and_mono():
    t = mine_typography(snap([
        el(0, "p", family='"Inter", sans-serif', area=5000),
        el(1, "div", family='"Inter", sans-serif', area=2000),
        el(2, "h1", family='"Playfair Display", serif', size="48px", area=300),
        el(3, "code", family='"JetBrains Mono", monospace', size="14px", area=200),
        el(4, "pre", family='"JetBrains Mono", monospace', size="14px", area=300),
    ]))
    assert t.body_family == "Inter" and t.body_stack == '"Inter", sans-serif'
    assert t.display_family == "Playfair Display"
    assert t.mono_family == "JetBrains Mono" and t.mono_stack == '"JetBrains Mono", monospace'
    assert t.families[0].family == "Inter" and not t.families[0].is_monospace
    assert any(f.is_monospace for f in t.families)
    assert abs(sum(f.weight for f in t.families) - 1) < 1e-9


def test_display_falls_back_to_body_and_mono_none():
    t = mine_typography(snap([el(0, "p", family="Inter, sans-serif"), el(1, "code", family="Inter, sans-serif")]))
    assert t.display_family == "Inter" and t.mono_family is None and t.mono_stack is None


def test_monospace_body():
    t = mine_typography(snap([el(0, "p", family='"Courier New", monospace'), el(1, "h1", family='"Courier New", monospace', size="40px")]))
    assert t.body_family == "Courier New" and t.mono_family is None  # code/pre yok
    assert t.families[0].is_monospace


def test_font_faces_and_links_passthrough():
    ff = [FontFace(family="Inter", src=["a.woff2"], weight="100 900", style="normal")]
    links = ["https://fonts.googleapis.com/css2?family=Inter"]
    t = mine_typography(snap([el(0, "p")], font_faces=ff, font_links=links))
    assert t.font_faces == ff and t.font_links == links


def test_empty_snapshot():
    t = mine_typography(snap([]))
    assert t.body_family == "sans-serif" and t.styles == {} and t.base_size_px == 16


def test_sample_snapshot_and_determinism():
    s = RawSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    t = mine_typography(s)
    assert t.body_family == "Inter"
    assert {"h1", "p"} <= set(t.styles)
    assert t.scale_ratio in TYPE_SCALE_RATIOS
    assert t.font_faces and t.font_faces[0].family == "Inter"
    assert t.model_dump_json() == mine_typography(s).model_dump_json()
    if "code" in t.styles:
        assert t.mono_family is not None
