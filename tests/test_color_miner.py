"""color_miner testleri (tarayıcısız)."""

from __future__ import annotations

import json
from pathlib import Path

from designdna.extractor.color_miner import (
    CLUSTER_DELTA_E,
    cluster_colors,
    effective_background,
    mine_colors,
)
from designdna.models import (
    STYLE_PROPERTIES,
    BoundingBox,
    ElementRecord,
    Gradient,
    RawSnapshot,
    TokenVar,
    Viewport,
)
from designdna.utils.color_math import delta_e_ok, hex_to_rgb

FIXTURE = Path(__file__).parent / "fixtures" / "sample_snapshot.json"
TRANSPARENT = "rgba(0, 0, 0, 0)"


def de(a: str, b: str) -> float:
    return delta_e_ok(hex_to_rgb(a), hex_to_rgb(b))


def el(idx, parent, tag="div", *, bg=TRANSPARENT, color="rgb(255, 255, 255)", text=0, area=10000.0,
       border=None, border_style="solid", border_width="1px", shadow="none", classes=None, href=False,
       input_type=None, role=None):
    styles = {k: "" for k in STYLE_PROPERTIES}
    styles.update({
        "color": color, "background-color": bg, "box-shadow": shadow,
        "font-size": "16px", "font-family": "Inter, sans-serif", "font-weight": "400",
    })
    for side in ("top", "right", "bottom", "left"):
        styles[f"border-{side}-width"] = border_width if border else "0px"
        styles[f"border-{side}-style"] = border_style if border else "none"
        styles[f"border-{side}-color"] = border or "rgb(0, 0, 0)"
    return ElementRecord(
        idx=idx, parent_idx=parent, depth=0 if parent is None else 1, tag=tag, classes=classes or [],
        role=role, input_type=input_type, href=href, text_length=text,
        bbox=BoundingBox(x=0, y=0, width=100, height=100), area=area, in_viewport=True, styles=styles,
    )


def snap(elements, bg="#0a0a0c", gradients=None, mode="dark"):
    return RawSnapshot(
        tool_version="0.1.0", source="file:///t.html", viewport=Viewport(name="desktop", width=1440, height=900),
        color_scheme="light", natural_mode=mode, dominant_background=bg, page_height=900.0,
        elements=elements, gradients=gradients or [],
    )


def dark_page():
    return snap([
        el(0, None, "html", bg="rgb(10, 10, 12)", area=1_000_000),
        el(1, 0, "body", area=1_000_000),
        el(2, 1, "div", bg="rgba(255, 255, 255, 0.04)", area=50_000, border="rgba(255, 255, 255, 0.08)"),
        el(3, 2, "p", text=40, color="rgb(237, 237, 239)", area=8000),
        el(4, 2, "span", text=10, color="rgb(138, 143, 152)", area=3000),
        el(5, 1, "button", bg="rgb(94, 106, 210)", text=5, color="rgb(255, 255, 255)", area=4000),
    ])


# ---------------------------------------------------------------- clustering

def test_cluster_merges_close_colors_into_heaviest():
    out = cluster_colors([("#101010", 5), ("#111111", 3), ("#ff0000", 4)])
    assert [c.hex for c in out] == ["#101010", "#ff0000"] or [c.hex for c in out] == ["#ff0000", "#101010"]
    dark = next(c for c in out if c.hex == "#101010")
    assert dark.count == 2 and abs(dark.weight - 8 / 12) < 1e-9
    assert [c.hex for c in out][0] == "#101010"
    assert abs(sum(c.weight for c in out) - 1) < 1e-9


def test_cluster_far_colors_stay_separate():
    out = cluster_colors([("#000000", 1), ("#ffffff", 1)])
    assert len(out) == 2 and de("#000000", "#ffffff") > CLUSTER_DELTA_E


def test_cluster_tie_by_hex_and_order_independent():
    a = cluster_colors([("#101010", 2), ("#111111", 2)])
    b = cluster_colors([("#111111", 2), ("#101010", 2)])
    assert [c.hex for c in a] == [c.hex for c in b] == ["#101010"]
    assert a[0].count == 2


def test_cluster_empty():
    assert cluster_colors([]) == []


# ---------------------------------------------------------------- effective bg

def test_effective_background_layers():
    s = dark_page()
    r, g, b = effective_background(s, 2)
    assert abs(r - (0.04 + 0.96 * 10 / 255)) < 1e-6
    assert effective_background(s, 1) == effective_background(s, 0)
    # kök opak değilse beyaz üstüne
    s2 = snap([el(0, None, "html"), el(1, 0, "div", bg="rgba(0, 0, 0, 0.5)")])
    assert abs(effective_background(s2, 1)[0] - 0.5) < 1e-6


# ---------------------------------------------------------------- roles

def test_dark_page_roles():
    a = mine_colors(dark_page())
    r = a.roles
    assert r.background.hex == "#0a0a0c"
    assert de(r.text_primary.hex, "#ededef") < 0.01
    assert de(r.text_muted.hex, "#8a8f98") < 0.01
    assert de(r.accent.hex, "#5e6ad2") < 0.01
    assert r.surface.hex != r.background.hex


def test_semi_transparent_border_composited():
    s = snap([
        el(0, None, "html", bg="rgb(10, 10, 12)", area=1_000_000),
        el(1, 0, "div", area=50_000, border="rgba(255, 255, 255, 0.08)"),
    ])
    r = mine_colors(s).roles
    assert r.border.raw == "rgba(255, 255, 255, 0.08)"
    got = hex_to_rgb(r.border.hex)
    exp = hex_to_rgb("#1e1e1f")
    assert all(abs(g - e) * 255 <= 1.01 for g, e in zip(got, exp))


def test_border_ignores_zero_width_and_none_style():
    s = snap([
        el(0, None, "html", bg="rgb(255,255,255)", color="rgb(0,0,0)"),
        el(1, 0, "div", border="rgb(255, 0, 0)", border_width="0px", area=1000),
        el(2, 0, "div", border="rgb(0, 255, 0)", border_style="none", area=1000),
        el(3, 0, "div", border="rgb(200, 200, 200)", area=100),
    ], bg="#ffffff", mode="light")
    assert mine_colors(s).roles.border.hex == "#c8c8c8"


def test_border_fallback_shifts_background():
    s = snap([el(0, None, "html", bg="rgb(255,255,255)", color="rgb(0,0,0)")], bg="#ffffff", mode="light")
    r = mine_colors(s).roles
    assert r.border.hex != "#ffffff" and r.border.weight == 0
    d = mine_colors(snap([el(0, None, "html", bg="rgb(10,10,12)")])).roles
    assert d.border.oklch[0] > d.background.oklch[0] + 0.05


def test_text_zero_length_ignored():
    s = snap([
        el(0, None, "html", bg="rgb(255,255,255)", color="rgb(0,0,0)", area=1_000_000),
        el(1, 0, "div", text=0, color="rgb(255, 0, 0)", area=900_000),
        el(2, 0, "p", text=5, color="rgb(20, 20, 20)", area=100),
    ], bg="#ffffff", mode="light")
    assert mine_colors(s).roles.text_primary.hex == "#141414"


def test_text_over_effective_background_composite():
    s = snap([
        el(0, None, "html", bg="rgb(0,0,0)", area=1_000_000),
        el(1, 0, "p", text=5, color="rgba(255, 255, 255, 0.5)", area=100),
    ], bg="#000000")
    assert mine_colors(s).roles.text_primary.hex == "#808080"


def test_text_muted_fallback_and_primary_fallback():
    s = snap([
        el(0, None, "html", bg="rgb(255,255,255)", color="rgb(0,0,0)", area=1_000_000),
        el(1, 0, "p", text=5, color="rgb(17, 17, 17)", area=100),
    ], bg="#ffffff", mode="light")
    r = mine_colors(s).roles
    assert r.text_muted.weight == 0
    assert r.text_muted.oklch[0] > r.text_primary.oklch[0] + 0.2
    empty = mine_colors(snap([el(0, None, "html", bg="rgb(10,10,12)")])).roles
    assert empty.text_primary.hex == "#ffffff"
    assert empty.accent.hex == empty.text_primary.hex


def test_surface_from_cards_and_fallback():
    s = snap([
        el(0, None, "html", bg="rgb(250,250,250)", color="rgb(0,0,0)", area=1_000_000),
        el(1, 0, "div", bg="rgb(255,255,255)", text=0, area=60_000, border="rgb(220,220,220)"),
        el(2, 1, "p", text=5, color="rgb(0,0,0)", area=100),
        el(3, 0, "div", bg="rgb(230, 235, 245)", area=90_000),
        el(4, 3, "h2", text=5, color="rgb(0,0,0)", area=100),
    ], bg="#fafafa", mode="light")
    surf = mine_colors(s).roles.surface
    assert surf.hex == "#e6ebf5"
    s2 = snap([el(0, None, "html", bg="rgb(10,10,12)")])
    sf = mine_colors(s2).roles
    assert sf.surface.weight == 0 and sf.surface.oklch[0] > sf.background.oklch[0]


def test_accent_selection_and_fallbacks():
    base = [el(0, None, "html", bg="rgb(255,255,255)", color="rgb(0,0,0)", area=1_000_000)]
    # kromatik buton > kromatik olmayan daha ağır buton
    s = snap(base + [
        el(1, 0, "button", bg="rgb(0, 0, 0)", text=3, area=9000),
        el(2, 0, "a", text=3, classes=["btn"], bg="rgb(220, 38, 38)", area=2000),
    ], bg="#ffffff", mode="light")
    assert mine_colors(s).roles.accent.hex == "#dc2626"
    # yalnız kromatik olmayan butonlar -> en kromatik buton arka planı
    s = snap(base + [el(1, 0, "button", bg="rgb(30, 30, 30)", text=3, area=500)], bg="#ffffff", mode="light")
    assert mine_colors(s).roles.accent.hex == "#1e1e1e"
    # aktif link rengi
    s = snap(base + [el(1, 0, "a", href=True, text=3, color="rgb(37, 99, 235)", area=500)], bg="#ffffff", mode="light")
    assert mine_colors(s).roles.accent.hex == "#2563eb"
    # hiçbiri -> text-primary
    s = snap(base + [el(1, 0, "p", text=3, color="rgb(10, 10, 10)", area=500)], bg="#ffffff", mode="light")
    r = mine_colors(s).roles
    assert r.accent.hex == r.text_primary.hex


def test_layered_cards_and_transparent_body_wrapper():
    s = snap([
        el(0, None, "html", area=1_000_000),
        el(1, 0, "body", area=1_000_000),
        el(2, 1, "div", bg="rgb(15, 15, 20)", area=900_000),  # wrapper
        el(3, 2, "div", bg="rgba(255, 255, 255, 0.06)", area=60_000, border="rgba(255,255,255,0.1)"),
        el(4, 3, "h3", text=5, color="rgb(240, 240, 240)", area=1000),
        el(5, 3, "div", bg="rgba(255, 255, 255, 0.06)", area=20_000, border="rgba(255,255,255,0.1)"),
        el(6, 5, "p", text=5, color="rgb(240, 240, 240)", area=1000),
    ], bg="#0f0f14")
    r = mine_colors(s).roles
    assert r.background.hex == "#0f0f14"
    assert r.surface.oklch[0] > r.background.oklch[0]
    assert de(r.text_primary.hex, "#f0f0f0") < 0.01


# ---------------------------------------------------------------- tokens

def test_token_priority_and_theme_filter():
    s = dark_page()
    toks = [
        TokenVar(name="--accent", value="#5f6bd3", kind="color", selector=":root"),
        TokenVar(name="--foreground", value="#eeeef0", kind="color", selector=":root"),
        TokenVar(name="--border", value="#ff00ff", kind="color", selector=":root"),  # paletteye uzak
        TokenVar(name="--text-muted", value="#8a8f98", kind="color", selector='[data-theme="light"]'),
    ]
    r = mine_colors(s, toks).roles
    assert r.accent.hex == "#5f6bd3" and r.accent.raw == "#5f6bd3"
    assert r.text_primary.hex == "#eeeef0"
    assert r.border.hex != "#ff00ff"
    # muted token'ı light seçici nedeniyle yok sayılır; sonuç yine kümelenmiş renk
    assert de(r.text_muted.hex, "#8a8f98") < 0.01


# ---------------------------------------------------------------- gradients / palette / determinism

def test_gradients_extracted_and_merged():
    g = lambda area, v="linear-gradient(90deg, red, blue)": Gradient(kind="linear", value=v, element_idx=0, area=area, colors=[])
    s = snap([el(0, None, "html", bg="rgb(10,10,12)")], gradients=[
        g(100), g(300), Gradient(kind="radial", value="radial-gradient(red, blue)", element_idx=0, area=100, colors=[]),
    ])
    gr = mine_colors(s).gradients
    assert [x.kind for x in gr] == ["linear", "radial"]
    assert abs(gr[0].weight - 0.8) < 1e-9 and abs(sum(x.weight for x in gr) - 1) < 1e-9


def test_palette_sorted_and_normalized():
    p = mine_colors(dark_page()).palette
    assert abs(sum(c.weight for c in p) - 1) < 1e-9
    keys = [(-c.weight, c.hex) for c in p]
    assert keys == sorted(keys)
    assert any("accent" in c.roles for c in p)


def test_sample_snapshot():
    snapshot = RawSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    a = mine_colors(snapshot)
    assert a.roles.background.hex == snapshot.dominant_background
    assert len(a.gradients) == len(snapshot.gradients) >= 1
    assert abs(sum(c.weight for c in a.palette) - 1) < 1e-9
    assert a.roles.accent.oklch[1] >= 0.05
    for role in (a.roles.surface, a.roles.text_primary, a.roles.text_muted, a.roles.border):
        assert len(role.hex) == 7
    assert mine_colors(snapshot).model_dump_json() == a.model_dump_json()


def test_deterministic_twice():
    s = dark_page()
    assert mine_colors(s).model_dump_json() == mine_colors(s).model_dump_json()
