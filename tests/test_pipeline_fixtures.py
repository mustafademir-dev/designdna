from __future__ import annotations

import json
from pathlib import Path

import pytest

from designdna.cache import load_capture_file
from designdna.extractor.pipeline import build_site_extraction
from designdna.utils.color_math import delta_e_ok, hex_to_rgb

ROOT = Path(__file__).parent
NAMES = ["neo_brutalist", "linear_dark", "stripe_clean"]


def _load(name):
    cap = load_capture_file(ROOT / "fixtures" / "snapshots" / f"{name}.capture.json")
    exp = json.loads((ROOT / "expected" / f"{name}.json").read_text(encoding="utf-8"))
    return cap, build_site_extraction(cap), exp


def _de(a, b):
    return delta_e_ok(hex_to_rgb(a), hex_to_rgb(b))


@pytest.fixture(params=NAMES)
def case(request):
    return (request.param, *_load(request.param))


def test_colors(case):
    name, cap, ex, exp = case
    roles = ex.colors.roles
    for key, want in exp.get("colors", {}).items():
        got = getattr(roles, key).hex
        options = want["any_of"] if isinstance(want, dict) else [want]
        assert any(_de(got, o) <= 0.05 for o in options), f"{name}.{key}: {got} not in {options}"


def test_palette_includes(case):
    name, cap, ex, exp = case
    for want in exp.get("palette_includes", []):
        assert any(_de(c.hex, want) <= 0.05 for c in ex.colors.palette), f"{name}: {want} yok"


def test_gradients(case):
    name, cap, ex, exp = case
    assert len(ex.colors.gradients) >= exp.get("gradients_min", 0)


def test_fonts(case):
    name, cap, ex, exp = case
    f = exp.get("fonts", {})
    t = ex.typography
    if f.get("body_family"):
        assert t.body_family.lower() == f["body_family"].lower()
    if f.get("display_family"):
        assert t.display_family.lower() == f["display_family"].lower()
    if f.get("mono_family"):
        assert (t.mono_family or "").lower() == f["mono_family"].lower()
    if f.get("body_is_monospace") is not None:
        body = next(u for u in t.families if u.family == t.body_family)
        assert body.is_monospace == f["body_is_monospace"]


def test_components(case):
    name, cap, ex, exp = case
    for ctype, want in exp.get("components", {}).items():
        comp = getattr(ex.components, ctype)
        assert comp is not None, f"{name}: {ctype} yok"
        if "radius_px" in want:
            assert abs(comp.border_radius_px - want["radius_px"]) <= 1, f"{name}.{ctype} radius"
        if "border_width_px" in want:
            assert abs(comp.border_width_px - want["border_width_px"]) <= 1, f"{name}.{ctype} border"
        if want.get("border_color"):
            assert comp.border_color is not None and _de(comp.border_color, want["border_color"]) <= 0.05
        if "shadow_contains" in want:
            assert want["shadow_contains"] in comp.box_shadow
        if want.get("has_shadow") is True:
            assert comp.box_shadow != "none"
        if want.get("has_shadow") is False:
            assert comp.box_shadow == "none"
        if want.get("has_backdrop") is True:
            assert comp.backdrop_filter != "none"
        if want.get("has_backdrop") is False:
            assert comp.backdrop_filter == "none"


def test_shadow_style(case):
    name, cap, ex, exp = case
    if exp.get("shadow_style"):
        assert ex.components.shadow_style == exp["shadow_style"]


def test_hover(case):
    name, cap, ex, exp = case
    for ctype, want in exp.get("hover", {}).items():
        comp = getattr(ex.components, ctype)
        assert comp is not None and comp.hover is not None, f"{name}.{ctype} hover yok"
        h = comp.hover
        if want.get("transform_changes") is not None:
            assert bool(h.transform) == want["transform_changes"]
        if want.get("background_changes") is not None:
            assert h.background_changes == want["background_changes"]
        if want.get("shadow_changes") is not None:
            assert h.shadow_changes == want["shadow_changes"]


def test_tokens(case):
    name, cap, ex, exp = case
    names = [t.name for t in ex.tokens]
    spec = exp.get("tokens", {})
    for n in spec.get("include", []):
        assert n in names
    for p in spec.get("exclude_prefixes", []):
        assert not any(n.startswith(p) for n in names)


def test_layout_spacing(case):
    name, cap, ex, exp = case
    if exp.get("spacing_base") is not None:
        assert ex.spacing.base == exp["spacing_base"]
    if exp.get("container_max_width_px") is not None:
        assert ex.layout.container_max_width is not None
        assert abs(ex.layout.container_max_width - exp["container_max_width_px"]) <= 1
    for bp in exp.get("breakpoints_include", []):
        assert bp in ex.layout.breakpoints


def test_counter(case):
    name, cap, ex, exp = case
    cb = exp.get("counter_background")
    if cb is None:
        assert ex.counter is None
    else:
        assert ex.counter is not None
        assert ex.counter.mode != ex.natural_mode
        assert _de(ex.counter.colors.background.hex, cb) <= 0.05


def test_natural_mode(case):
    name, cap, ex, exp = case
    assert ex.natural_mode == exp["natural_mode"]


def test_mobile_is_not_color_or_token_source(case):
    name, cap, ex, exp = case
    if cap.mobile is None:
        pytest.skip("mobile yok")
    from designdna.models import CustomProperty

    elements = [
        e.model_copy(
            update={
                "styles": {
                    k: ("rgb(255, 0, 0)" if "color" in k.lower() else v) for k, v in e.styles.items()
                }
            }
        )
        for e in cap.mobile.elements
    ]
    props = list(cap.mobile.custom_properties) + [
        CustomProperty(name="--accent", value="#ff0000", selector=":root")
    ]
    mobile = cap.mobile.model_copy(update={"elements": elements, "custom_properties": props})
    ex2 = build_site_extraction(cap.model_copy(update={"mobile": mobile}))
    assert ex2.colors == ex.colors
    assert ex2.tokens == ex.tokens
    assert ex2.typography == ex.typography
