from __future__ import annotations

import math

import pytest

from designdna.utils import color_math as cm


def approx3(a, b, tol=1e-3):
    return all(abs(x - y) <= tol for x, y in zip(a, b)) and len(a) == len(b)


def test_srgb_linear_roundtrip():
    for v in (0.0, 0.01, 0.2, 0.5, 0.9, 1.0):
        assert cm.linear_to_srgb(cm.srgb_to_linear(v)) == pytest.approx(v, abs=1e-9)
    assert cm.srgb_to_linear(0.5) == pytest.approx(0.2140411, abs=1e-6)


def test_white_black_oklab():
    assert approx3(cm.rgb_to_oklab((1, 1, 1)), (1.0, 0.0, 0.0), 1e-4)
    assert approx3(cm.rgb_to_oklab((0, 0, 0)), (0.0, 0.0, 0.0), 1e-9)


def test_red_oklch_reference():
    L, C, H = cm.rgb_to_oklch((1, 0, 0))
    assert L == pytest.approx(0.628, abs=1e-3)
    assert C == pytest.approx(0.2577, abs=1e-3)
    assert H == pytest.approx(29.23, abs=0.05)


def test_gray_has_zero_hue():
    L, C, H = cm.rgb_to_oklch((0.5, 0.5, 0.5))
    assert C < 1e-4 and H == 0.0


def test_oklab_roundtrip():
    for rgb in [(0.1, 0.5, 0.9), (0.9, 0.2, 0.3), (0.04, 0.04, 0.05), (1, 1, 0)]:
        back = cm.oklab_to_rgb(cm.rgb_to_oklab(rgb))
        assert approx3(back, rgb, 1e-5)
        lch = cm.oklab_to_oklch(cm.rgb_to_oklab(rgb))
        assert approx3(cm.oklab_to_rgb(cm.oklch_to_oklab(lch)), rgb, 1e-5)


def test_hex_roundtrip_all_greys():
    for i in range(256):
        h = f"#{i:02x}{i:02x}{i:02x}"
        assert cm.rgb_to_hex(cm.hex_to_rgb(h)) == h
    assert cm.rgb_to_hex((1.2, -0.3, 0.5)) == "#ff0080"
    with pytest.raises(ValueError):
        cm.hex_to_rgb("nope")


def test_contrast():
    assert cm.contrast_ratio((0, 0, 0), (1, 1, 1)) == pytest.approx(21.0)
    assert cm.contrast_ratio((1, 1, 1), (0, 0, 0)) == pytest.approx(21.0)
    assert cm.contrast_ratio((1, 1, 1), (1, 1, 1)) == pytest.approx(1.0)
    assert cm.contrast_ratio(cm.hex_to_rgb("#777777"), (1, 1, 1)) == pytest.approx(4.48, abs=0.01)
    assert cm.relative_luminance((1, 1, 1)) == pytest.approx(1.0)


def test_parse_hex_forms():
    assert cm.parse_color("#fff") == (1.0, 1.0, 1.0, 1.0)
    assert cm.parse_color("#F00") == (1.0, 0.0, 0.0, 1.0)
    r = cm.parse_color("#0f08")
    assert r[:3] == (0.0, 1.0, 0.0) and r[3] == pytest.approx(0x88 / 255)
    assert cm.parse_color("#0a0a0c") == (10 / 255, 10 / 255, 12 / 255, 1.0)
    assert cm.parse_color("#ff000080")[3] == pytest.approx(128 / 255)


def test_parse_rgb_forms():
    assert cm.parse_color("rgb(10, 10, 12)") == (10 / 255, 10 / 255, 12 / 255, 1.0)
    assert cm.parse_color("rgba(255, 255, 255, 0.08)") == (1.0, 1.0, 1.0, 0.08)
    assert cm.parse_color("rgb(0 0 0 / 50%)") == (0.0, 0.0, 0.0, 0.5)
    assert cm.parse_color("rgb(100% 0% 0%)") == (1.0, 0.0, 0.0, 1.0)
    assert cm.parse_color("rgb(0 128 255 / 0.25)") == (0.0, 128 / 255, 1.0, 0.25)
    assert cm.parse_color("RGB(255,0,0)") == (1.0, 0.0, 0.0, 1.0)


def test_parse_hsl_forms():
    r = cm.parse_color("hsl(0, 100%, 50%)")
    assert approx3(r, (1, 0, 0, 1), 1e-9)
    r = cm.parse_color("hsl(120deg 100% 25% / 0.5)")
    assert approx3(r, (0, 0.5, 0, 0.5), 1e-9)
    r = cm.parse_color("hsla(240, 100%, 50%, 0.3)")
    assert approx3(r, (0, 0, 1, 0.3), 1e-9)
    assert cm.parse_color("hsl(0.5turn 100% 50%)") is not None


def test_parse_oklch_forms():
    r = cm.parse_color("oklch(0.628 0.2577 29.23)")
    assert cm.rgb_to_hex(r[:3]) == "#ff0000"
    r2 = cm.parse_color("oklch(62.8% 0.2577 29.23 / 40%)")
    assert cm.rgb_to_hex(r2[:3]) == "#ff0000" and r2[3] == pytest.approx(0.4)
    assert cm.parse_color("oklch(1 0 0)") == pytest.approx((1.0, 1.0, 1.0, 1.0), abs=1e-3)


def test_parse_named_and_color_fn():
    assert cm.parse_color("transparent") == (0.0, 0.0, 0.0, 0.0)
    for n in ("black", "white", "red", "green", "blue", "gray", "grey", "yellow", "orange", "purple", "pink"):
        assert cm.parse_color(n) is not None
    assert cm.parse_color("White") == (1.0, 1.0, 1.0, 1.0)
    assert cm.parse_color("color(srgb 1 0 0)") == (1.0, 0.0, 0.0, 1.0)
    assert cm.parse_color("color(srgb 1 0 0 / 0.5)") == (1.0, 0.0, 0.0, 0.5)


@pytest.mark.parametrize(
    "bad",
    ["", "currentcolor", "currentColor", "inherit", "var(--x)", "#12", "#ggg", "rgb(1,2)", "foo", "rgb(a b c)", "hsl(1 2)", "#12345"],
)
def test_parse_invalid(bad):
    assert cm.parse_color(bad) is None


def test_gamut_mapping():
    lch = (0.7, 0.4, 150.0)
    raw = cm.oklab_to_rgb(cm.oklch_to_oklab(lch))
    assert not cm.in_gamut(raw)
    rgb = cm.gamut_map_oklch(lch)
    assert cm.in_gamut(rgb) and all(0 <= c <= 1 for c in rgb)
    L, C, H = cm.rgb_to_oklch(rgb)
    assert L == pytest.approx(0.7, abs=0.01)
    assert C < 0.4
    assert abs(H - 150.0) < 2.0
    assert cm.oklch_to_rgb(lch) == rgb


def test_gamut_map_in_gamut_unchanged():
    rgb = (0.2, 0.4, 0.6)
    assert approx3(cm.oklch_to_rgb(cm.rgb_to_oklch(rgb)), rgb, 1e-6)
    assert cm.gamut_map_oklch((1.2, 0.1, 10)) == (1.0, 1.0, 1.0) or all(0 <= c <= 1 for c in cm.gamut_map_oklch((1.2, 0.1, 10)))


def test_in_gamut():
    assert cm.in_gamut((0, 0.5, 1))
    assert not cm.in_gamut((1.01, 0.5, 0.5))
    assert not cm.in_gamut((-0.01, 0.5, 0.5))


def test_composite():
    bg = cm.hex_to_rgb("#0a0a0c")
    out = cm.composite(cm.parse_color("rgba(255,255,255,0.08)"), bg)
    got = [round(c * 255) for c in out]
    for g, e in zip(got, (0x1D, 0x1D, 0x1F)):
        assert abs(g - e) <= 1
    assert cm.composite((1, 0, 0, 1.0), (0, 0, 1)) == (1, 0, 0)
    assert cm.composite((1, 0, 0, 0.0), (0, 0, 1)) == (0, 0, 1)
    assert cm.composite((1, 0, 0, 0.5), (0, 0, 1)) == (0.5, 0, 0.5)


def test_composite_over_layers():
    out = cm.composite_over([(1, 0, 0, 0.5), (0, 0, 1, 0.5)], (1, 1, 1))
    assert approx3(out, (0.5, 0.25, 0.75), 1e-9)
    assert cm.composite_over([]) == (1, 1, 1)


def test_delta_e_ok():
    assert cm.delta_e_ok((1, 0, 0), (1, 0, 0)) == 0.0
    assert cm.delta_e_ok((0, 0, 0), (1, 1, 1)) == pytest.approx(1.0, abs=1e-3)
    assert cm.delta_e_ok((1, 0, 0), (0, 0, 1)) == cm.delta_e_ok((0, 0, 1), (1, 0, 0))


def test_normalize_hex():
    assert cm.normalize_hex("rgb(10, 10, 12)") == "#0a0a0c"
    assert cm.normalize_hex("#FFF") == "#ffffff"
    assert cm.normalize_hex("rgba(0,0,0,0.5)") == "#808080"
    got = cm.normalize_hex("rgba(255,255,255,0.08)", cm.hex_to_rgb("#0a0a0c"))
    assert all(abs(int(got[i : i + 2], 16) - e) <= 1 for i, e in ((1, 0x1D), (3, 0x1D), (5, 0x1F)))
    assert cm.normalize_hex("transparent", (0, 0, 0)) == "#000000"
    assert cm.normalize_hex("var(--x)") is None


def test_oklch_css():
    assert cm.oklch_css((1, 0, 0)) == "oklch(0.628 0.258 29.23)"
    assert cm.oklch_css((1, 1, 1)) == "oklch(1.000 0.000 0.00)"


def test_hsl_components():
    assert approx3(cm.hsl_components((1, 0, 0)), (0, 100, 50), 1e-9)
    assert approx3(cm.hsl_components((0, 0, 1)), (240, 100, 50), 1e-9)
    assert approx3(cm.hsl_components((1, 1, 1)), (0, 0, 100), 1e-9)
    assert approx3(cm.hsl_components((0, 0, 0)), (0, 0, 0), 1e-9)
    h, s, l = cm.hsl_components((0.5, 0.5, 0.5))
    assert s == 0 and l == pytest.approx(50)
    assert math.isfinite(cm.hsl_components((0.2, 0.7, 0.4))[0])
