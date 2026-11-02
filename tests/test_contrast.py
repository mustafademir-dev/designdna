from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from designdna.cache import load_capture_file
from designdna.extractor.pipeline import build_site_extraction
from designdna.models import ColorToken, SiteExtraction
from designdna.synthesizer.blender import blend, ensure_contrast
from designdna.utils.color_math import contrast_ratio, hex_to_rgb, oklch_to_rgb, rgb_to_hex, rgb_to_oklch

SNAP = Path(__file__).parent / "fixtures" / "snapshots"
NAMES = ("neo_brutalist", "linear_dark", "stripe_clean")


def _cr(a, b):
    return contrast_ratio(hex_to_rgb(a), hex_to_rgb(b))


@pytest.fixture(scope="module")
def ex():
    return {n: build_site_extraction(load_capture_file(SNAP / f"{n}.capture.json")) for n in NAMES}


def _token(hx):
    return ColorToken(hex=hx, oklch=rgb_to_oklch(hex_to_rgb(hx)))


def _tricky(base: SiteExtraction, source="tricky://low") -> SiteExtraction:
    """Neredeyse görünmez metin/kenarlık, orta tonlu accent ve zıt zemin."""
    roles = base.colors.roles.model_copy(
        update={
            "background": _token("#808080"),
            "surface": _token("#8a8a8a"),
            "text_primary": _token("#858585"),
            "text_muted": _token("#7c7c7c"),
            "border": _token("#838383"),
            "accent": _token("#8a8a00"),
        }
    )
    colors = base.colors.model_copy(update={"roles": roles})
    return base.model_copy(update={"colors": colors, "source": source, "counter": None})


def _assert_theme(t):
    for fg in (t.text_primary, t.text_muted):
        assert _cr(fg, t.background) >= 4.5, (fg, t.background)
        assert _cr(fg, t.surface) >= 4.5, (fg, t.surface)
    assert _cr(t.accent_foreground, t.accent) >= 4.5
    for ref in (t.background, t.surface):
        assert _cr(t.border, ref) >= 3.0
    assert _cr(t.secondary_foreground, t.secondary) >= 4.5
    assert _cr(t.destructive_foreground, t.destructive) >= 4.5


def _cases(ex):
    singles = [([ex[n]], None) for n in NAMES]
    pairs = [([ex[a], ex[b]], [70, 30]) for a, b in itertools.permutations(NAMES, 2)]
    triple = [([ex[n] for n in NAMES], [50, 30, 20]), ([ex[n] for n in NAMES], None)]
    low = [([ex["neo_brutalist"], ex["linear_dark"]], [95, 5])]
    tricky = [
        ([_tricky(ex["linear_dark"])], None),
        ([_tricky(ex["neo_brutalist"])], None),
        ([_tricky(ex["stripe_clean"])], None),
        ([_tricky(ex["neo_brutalist"]), ex["stripe_clean"]], [60, 40]),
    ]
    return singles + pairs + triple + low + tricky


def test_all_blends_meet_contrast(ex):
    for exs, w in _cases(ex):
        ds, rep = blend(exs, w)
        _assert_theme(ds.light)
        _assert_theme(ds.dark)
        for fix in rep.contrast_fixes:
            if fix.achieved:
                assert fix.ratio_after >= fix.target
            assert fix.original != fix.adjusted or not fix.achieved


def test_tricky_produces_fixes(ex):
    ds, rep = blend([_tricky(ex["linear_dark"])])
    roles = {(f.theme, f.role) for f in rep.contrast_fixes}
    assert ("dark", "text-primary") in roles or ("light", "text-primary") in roles
    assert any(f.role == "border" for f in rep.contrast_fixes)


def test_ensure_noop_when_ok():
    out, ratio, ok = ensure_contrast("#000000", ["#ffffff"], 4.5)
    assert out == "#000000" and ok and ratio == pytest.approx(21.0)


def test_ensure_preserves_hue_chroma():
    color = "#6a7fb0"  # orta ton, mavi
    bg = "#ffffff"
    out, ratio, ok = ensure_contrast(color, [bg], 4.5)
    assert ok and ratio >= 4.5 and out != color
    l0, c0, h0 = rgb_to_oklch(hex_to_rgb(color))
    l1, c1, h1 = rgb_to_oklch(hex_to_rgb(out))
    assert l1 < l0  # beyazdan uzaklaştı
    assert abs(h1 - h0) < 6
    assert abs(c1 - c0) < 0.04
    # adım: 0.02'nin tam katı (8 bit yuvarlama toleransıyla)
    steps = (l0 - l1) / 0.02
    assert abs(steps - round(steps)) < 0.1


def test_ensure_direction_up_on_dark():
    out, ratio, ok = ensure_contrast("#303040", ["#101015"], 4.5)
    assert ok and ratio >= 4.5
    assert rgb_to_oklch(hex_to_rgb(out))[0] > rgb_to_oklch(hex_to_rgb("#303040"))[0]


def test_ensure_multiple_against_uses_min():
    out, ratio, ok = ensure_contrast("#777777", ["#ffffff", "#dddddd"], 4.5)
    assert ok
    assert _cr(out, "#ffffff") >= 4.5 and _cr(out, "#dddddd") >= 4.5
    assert ratio == pytest.approx(min(_cr(out, "#ffffff"), _cr(out, "#dddddd")), abs=1e-6)


def test_ensure_fallback_white_black():
    # L'si 40 adımda hedefe yetişmeyen: orta gri zeminlerde 4.5 için fallback gerekir
    out, ratio, ok = ensure_contrast("#808080", ["#808080", "#7a7a7a", "#868686"], 4.5)
    assert out in ("#ffffff", "#000000") or ok
    if ok:
        assert ratio >= 4.5
    # imkânsız hedef: en yüksek oran seçilir, achieved False
    out, ratio, ok = ensure_contrast("#808080", ["#808080"], 30.0)
    assert not ok and out in ("#ffffff", "#000000")
    assert ratio == pytest.approx(max(_cr("#ffffff", "#808080"), _cr("#000000", "#808080")))


def test_ensure_step_limit_uses_fallback():
    # 0.02 * 40 = 0.8: L=0.96 -> 0.16'ya iner; 20:1 bunun ötesinde
    out, ratio, ok = ensure_contrast("#f0f0f0", ["#ffffff"], 20.0)
    assert out == "#000000" and ok
