from __future__ import annotations

from pathlib import Path

import pytest

from designdna.cache import load_capture_file
from designdna.errors import DesignDNAError
from designdna.extractor.pipeline import build_site_extraction
from designdna.models import STANDARD_RADII
from designdna.synthesizer.blender import (
    ELIGIBILITY_THRESHOLD,
    blend,
    normalize_weights,
    quantize_radius,
    quantize_spacing,
)
from designdna.utils.color_math import delta_e_ok, hex_to_rgb

SNAP = Path(__file__).parent / "fixtures" / "snapshots"


@pytest.fixture(scope="module")
def ex():
    return {
        n: build_site_extraction(load_capture_file(SNAP / f"{n}.capture.json"))
        for n in ("neo_brutalist", "linear_dark", "stripe_clean")
    }


def _roles(ds, name):
    return next(s for s in ds.sources if name in s.source).roles


def test_normalize_weights():
    assert normalize_weights([7, 3]) == pytest.approx([0.7, 0.3])
    assert normalize_weights([None, None, None]) == pytest.approx([1 / 3] * 3)
    assert normalize_weights([1, None]) == pytest.approx([0.5, 0.5])
    assert sum(normalize_weights([5, 1, 1, 3])) == pytest.approx(1.0)
    assert normalize_weights([1]) == [1.0]


def test_quantize():
    assert quantize_radius(0) == 0
    assert quantize_radius(3) == 2  # eşitlikte küçük
    assert quantize_radius(5) == 4
    assert quantize_radius(10) == 8
    assert quantize_radius(14) == 12
    assert quantize_radius(20) == 16
    assert quantize_radius(41) == 9999
    assert quantize_radius(9999) == 9999
    for px in range(0, 41):
        assert quantize_radius(px) in STANDARD_RADII
    assert quantize_spacing(5) == 4
    assert quantize_spacing(10) == 8
    assert quantize_spacing(20) == 16
    assert quantize_spacing(30) == 32
    assert quantize_spacing(70) in (64, 80)
    assert quantize_spacing(500) == 128


def test_linear_70_neo_30(ex):
    ds, rep = blend([ex["linear_dark"], ex["neo_brutalist"]], [70, 30])
    assert [s.normalized_weight for s in rep.sources] == pytest.approx([0.7, 0.3])
    assert all(s.eligible for s in rep.sources)
    assert ds.base_mode == "dark"
    lin, neo = _roles(ds, "linear"), _roles(ds, "neo")
    for r in ("background", "surface", "text-primary", "text-muted", "border", "font-body", "font-mono", "spacing", "layout"):
        assert r in lin
    # grup 3 üçüncü kaynak yok -> 2. kaynak (neo)
    assert set(neo) == {"accent", "radius-control", "hover-style", "shadow", "font-display", "radius-card"}
    # değerler
    lin_ex, neo_ex = ex["linear_dark"], ex["neo_brutalist"]
    assert delta_e_ok(hex_to_rgb(ds.dark.background), hex_to_rgb(lin_ex.colors.roles.background.hex)) < 0.01
    assert ds.dark.accent == neo_ex.colors.roles.accent.hex
    assert ds.typography.sans.family == lin_ex.typography.body_family
    assert ds.typography.sans.source == lin_ex.source
    assert ds.typography.display.source == neo_ex.source
    assert ds.radius["default"] == 0 and ds.components.button.radius_px == 0
    assert ds.components.card.radius_px == 0
    assert ds.shadows.style == "hard"
    assert ds.motion.hover_transform is not None
    assert ds.spacing_base == lin_ex.spacing.base
    assert not rep.warnings or all("kontrast" not in w for w in rep.warnings)
    assert {r.role for r in rep.roles} >= {"accent", "shadow", "radius-card"}


def test_three_sources(ex):
    ds, rep = blend([ex["neo_brutalist"], ex["stripe_clean"], ex["linear_dark"]], [50, 30, 20])
    assert all(s.eligible for s in rep.sources)
    neo, stripe, lin = _roles(ds, "neo"), _roles(ds, "stripe"), _roles(ds, "linear")
    assert set(neo) == {"background", "surface", "text-primary", "text-muted", "border", "font-body", "font-mono", "spacing", "layout"}
    assert set(stripe) == {"accent", "radius-control", "hover-style"}
    assert set(lin) == {"shadow", "font-display", "radius-card"}
    assert ds.base_mode == "light"
    assert ds.typography.display.source == ex["linear_dark"].source
    assert ds.shadows.style == "none" and ds.shadows.md == "none"
    assert ds.components.card.shadow == "none"
    assert ds.components.card.radius_px == 8
    assert ds.components.button.radius_px == 12
    # türetilmiş koyu temada accent yalnızca hafifçe sönümlenir
    assert delta_e_ok(hex_to_rgb(ds.dark.accent), hex_to_rgb(ex["stripe_clean"].colors.roles.accent.hex)) < 0.05


def test_low_weight_gets_no_roles(ex):
    ds, rep = blend([ex["neo_brutalist"], ex["linear_dark"]], [95, 5])
    low = next(s for s in rep.sources if "linear" in s.source)
    assert low.eligible is False and low.normalized_weight == pytest.approx(0.05)
    assert _roles(ds, "linear") == []
    assert len(_roles(ds, "neo")) == 15
    assert any("eşiğinin altında" in w and "linear" in w for w in rep.warnings)
    assert all(a.source == ex["neo_brutalist"].source for a in rep.roles)
    assert ELIGIBILITY_THRESHOLD == 0.2


def test_threshold_boundary(ex):
    _, rep = blend([ex["neo_brutalist"], ex["linear_dark"]], [8, 2])
    assert all(s.eligible for s in rep.sources)


def test_low_third_source_falls_back(ex):
    ds, rep = blend([ex["neo_brutalist"], ex["stripe_clean"], ex["linear_dark"]], [60, 35, 5])
    assert _roles(ds, "linear") == []
    assert set(_roles(ds, "stripe")) >= {"accent", "shadow", "font-display", "radius-card"}
    assert rep.warnings


def test_single_source(ex):
    for name, e in ex.items():
        ds, rep = blend([e])
        assert ds.sources[0].weight == 1.0
        assert len(ds.sources[0].roles) == 15
        assert ds.base_mode == e.natural_mode
        assert rep.warnings == [] or all("eşik" not in w for w in rep.warnings)


def test_equal_weights_default(ex):
    ds, _ = blend([ex["neo_brutalist"], ex["linear_dark"], ex["stripe_clean"]])
    assert [s.weight for s in ds.sources] == pytest.approx([1 / 3] * 3)
    assert _roles(ds, "neo")[0] == "background"  # eşitlikte girdi sırası


def test_errors(ex):
    with pytest.raises(DesignDNAError):
        blend([])
    with pytest.raises(DesignDNAError):
        blend([ex["neo_brutalist"]], [1, 2])


def test_derived_counter_theme(ex):
    ds, rep = blend([ex["linear_dark"]])
    assert rep.counter_theme == "derived"
    from designdna.utils.color_math import rgb_to_oklch

    l_bg = rgb_to_oklch(hex_to_rgb(ds.light.background))[0]
    l_surface = rgb_to_oklch(hex_to_rgb(ds.light.surface))[0]
    assert 0.97 - 0.005 <= l_bg <= 0.99 + 0.005
    assert 0.93 - 0.005 <= l_surface <= 0.96 + 0.005
    ds, rep = blend([ex["neo_brutalist"]])
    assert rep.counter_theme == "derived"
    assert ds.base_mode == "light"
    assert 0.12 - 0.005 <= rgb_to_oklch(hex_to_rgb(ds.dark.background))[0] <= 0.16 + 0.005
    assert 0.18 - 0.005 <= rgb_to_oklch(hex_to_rgb(ds.dark.surface))[0] <= 0.22 + 0.005


def test_captured_counter_theme(ex):
    ds, rep = blend([ex["stripe_clean"]])
    assert rep.counter_theme == "captured"
    assert ds.base_mode == "light"
    assert delta_e_ok(hex_to_rgb(ds.dark.background), hex_to_rgb("#0a1929")) <= 0.03
    assert ds.dark.accent == ex["stripe_clean"].counter.colors.accent.hex


def test_quantized_outputs(ex):
    ds, _ = blend([ex["stripe_clean"], ex["neo_brutalist"]], [60, 40])
    for v in ds.radius.values():
        assert v in STANDARD_RADII
    for comp in (ds.components.button, ds.components.input, ds.components.card):
        assert comp.radius_px in STANDARD_RADII
        for p in comp.padding:
            assert p == quantize_spacing(p)
    vals = list(ds.spacing.values())
    assert vals == sorted(set(vals))
    assert list(ds.spacing)[:2] == ["0", "1"]
    for v in vals:
        assert v == quantize_spacing(v)
    r = ds.radius
    assert r["none"] <= r["sm"] <= r["md"] <= r["lg"] <= r["xl"] <= r["full"]


def test_typography_scale(ex):
    ds, _ = blend([ex["linear_dark"]])
    t = ds.typography
    assert t.sizes["base"] == t.base_size_px
    assert t.sizes["lg"] == round(t.base_size_px * t.scale_ratio, 2)
    assert t.sizes["xs"] == round(t.base_size_px * t.scale_ratio**-2, 2)
    assert t.sizes["5xl"] == round(t.base_size_px * t.scale_ratio**6, 2)
    assert list(t.sizes) == ["xs", "sm", "base", "lg", "xl", "2xl", "3xl", "4xl", "5xl"]
    assert t.line_heights["tight"] < t.line_heights["normal"] < t.line_heights["relaxed"]
    assert t.mono.stack.endswith("monospace")


def test_layout_defaults_and_breakpoints(ex):
    ds, _ = blend([ex["stripe_clean"]])
    assert ds.layout.container_max_width == 1100
    assert ds.layout.breakpoints["md"] == 800 and ds.layout.breakpoints["xl"] == 1200
    bp = list(ds.layout.breakpoints.values())
    assert bp == sorted(bp) and len(set(bp)) == 5


def test_determinism(ex):
    a = blend([ex["linear_dark"], ex["neo_brutalist"], ex["stripe_clean"]], [5, 3, 2])
    b = blend([ex["linear_dark"], ex["neo_brutalist"], ex["stripe_clean"]], [5, 3, 2])
    assert a[0].model_dump_json() == b[0].model_dump_json()
    assert a[1].model_dump_json() == b[1].model_dump_json()


@pytest.mark.parametrize(
    "raw,want",
    [
        ("matrix(1, 0, 0, 1, -2, -2)", "translate(-2px, -2px)"),
        ("matrix(1, 0, 0, 1, 0, -4.50)", "translate(0px, -4.5px)"),
        ("matrix(1.05, 0, 0, 1.05, 0, 0)", "scale(1.05)"),
        ("matrix(1.1, 0, 0, 1, 0, 0)", "scale(1.1, 1)"),
        ("matrix(1.05, 0, 0, 1.05, 0, -4)", "translate(0px, -4px) scale(1.05)"),
        ("matrix3d(1,0,0,0,0,1,0,0,0,0,1,0,3,4,0,1)", "translate(3px, 4px)"),
        ("matrix3d(1,0,0,0,0,1,0,0,0,0,1,0,3,4,5,1)", "translate3d(3px, 4px, 5px)"),
        ("matrix(0.7, 0.7, -0.7, 0.7, 0, 0)", "matrix(0.7, 0.7, -0.7, 0.7, 0, 0)"),
        ("none", None),
    ],
)
def test_fmt_transform(raw, want):
    from designdna.synthesizer.blender import _fmt_transform

    assert _fmt_transform(raw) == want


def test_component_hover_transform_readable_and_measured_flags(ex):
    for e in ex.values():
        ds, _ = blend([e])
        for comp in (ds.components.button, ds.components.card, ds.components.input):
            if comp.hover and comp.hover.transform:
                assert "matrix" not in comp.hover.transform
        if ds.motion.hover_transform:
            assert "matrix" not in ds.motion.hover_transform
        assert ds.motion.measured == (any(
            s is not None and s.hover is not None for s in (e.components.button, e.components.input, e.components.card)
        ))
        assert ds.layout.container_measured == bool(e.layout.container_max_width)
        assert ds.layout.grid_measured == bool(e.layout.grid_columns)


def test_unmeasured_defaults_flagged(ex):
    e = ex["stripe_clean"]
    layout = e.layout.model_copy(update={"container_max_width": None, "grid_columns": []})
    comps = e.components.model_copy(update={"button": None, "input": None, "card": None})
    ds, _ = blend([e.model_copy(update={"layout": layout, "components": comps})])
    assert ds.layout.container_measured is False and ds.layout.grid_measured is False
    assert ds.motion.measured is False
