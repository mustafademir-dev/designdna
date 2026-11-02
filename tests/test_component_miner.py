from __future__ import annotations

from pathlib import Path

from designdna.extractor.component_miner import (
    classify_element,
    mine_components,
    parse_shadows,
)
from designdna.models import STYLE_PROPERTIES, HoverDiff, RawSnapshot

FIXTURE = Path(__file__).parent / "fixtures" / "sample_snapshot.json"
DEFAULTS = {p: "0px" for p in STYLE_PROPERTIES}
DEFAULTS.update(
    {
        "color": "rgb(0, 0, 0)",
        "background-color": "rgba(0, 0, 0, 0)",
        "box-shadow": "none",
        "backdrop-filter": "none",
        "border-top-style": "none",
        "border-right-style": "none",
        "border-bottom-style": "none",
        "border-left-style": "none",
        "display": "block",
        "max-width": "none",
        "grid-template-columns": "none",
        "transform": "none",
    }
)


def el(idx, parent, tag="div", *, w=200, h=100, text=0, classes=(), role=None, itype=None, **styles):
    st = dict(DEFAULTS)
    st.update({k.replace("_", "-"): v for k, v in styles.items()})
    return {
        "idx": idx,
        "parent_idx": parent,
        "depth": 0 if parent is None else 1,
        "tag": tag,
        "classes": list(classes),
        "role": role,
        "input_type": itype,
        "text_length": text,
        "bbox": {"x": 0, "y": 0, "width": w, "height": h},
        "area": w * h,
        "in_viewport": True,
        "styles": st,
    }


def snap(elements) -> RawSnapshot:
    return RawSnapshot.model_validate(
        {
            "tool_version": "t",
            "source": "file:///x.html",
            "viewport": {"name": "desktop", "width": 1440, "height": 900},
            "color_scheme": "light",
            "natural_mode": "light",
            "dominant_background": "#ffffff",
            "page_height": 900,
            "elements": elements,
        }
    )


def border(w, color):
    return {
        f"border_{s}_{p}": v
        for s in ("top", "right", "bottom", "left")
        for p, v in (("width", w), ("style", "solid"), ("color", color))
    }


def test_parse_shadows():
    layers = parse_shadows("rgba(0, 0, 0, 0.1) 0px 1px 3px 0px, rgba(0, 0, 0, 0.06) 0px 1px 2px -1px")
    assert len(layers) == 2
    assert layers[0].y == 1 and layers[0].blur == 3 and layers[1].spread == -1
    hard = parse_shadows("rgb(0, 0, 0) 4px 4px 0px 0px")
    assert hard[0].blur == 0 and hard[0].x == 4 and hard[0].visible
    assert not parse_shadows("rgba(0, 0, 0, 0) 0px 0px 0px 0px")[0].visible
    assert parse_shadows("none") == []
    assert parse_shadows("rgb(0, 0, 0) 0px 0px 0px 1px inset")[0].inset


def test_classify_buttons_inputs():
    s = snap(
        [
            el(0, None, "body", w=1440, h=900),
            el(1, 0, "button", w=100, h=40, text=5),
            el(2, 0, "a", w=100, h=40, text=5, classes=["btn-primary"]),
            el(3, 0, "div", w=100, h=40, text=5, role="button"),
            el(4, 0, "input", itype="submit"),
            el(5, 0, "input", itype="email"),
            el(6, 0, "input"),
            el(7, 0, "textarea"),
            el(8, 0, "input", itype="checkbox"),
            el(9, 0, "a", w=100, h=20, text=5, classes=["link"]),
        ]
    )
    got = [classify_element(e, s) for e in s.elements]
    assert got == [None, "button", "button", "button", "button", "input", "input", "input", None, None]


def test_card_rules_and_wrapper_exclusion():
    s = snap(
        [
            el(0, None, "body", w=1440, h=900),
            # tam sayfa sarmalayıcı: kenarlıklı ama dışlanmalı
            el(1, 0, "div", w=1400, h=300, **border("1px", "rgb(0, 0, 0)")),
            el(2, 1, "h3", w=100, h=30, text=5),
            # gerçek kart: gölge, metinli torun
            el(3, 0, "div", w=300, h=200, box_shadow="rgba(0, 0, 0, 0.1) 0px 4px 6px -1px"),
            el(4, 3, "p", w=100, h=20, text=30),
            # görünmez kutu (arka plan yok): kart değil
            el(5, 0, "div", w=300, h=200),
            el(6, 5, "p", w=100, h=20, text=30),
            # çok küçük
            el(7, 0, "div", w=40, h=40, **border("1px", "rgb(0, 0, 0)")),
            el(8, 7, "p", w=10, h=10, text=3),
            # metinsiz torun yok
            el(9, 0, "div", w=300, h=200, **border("2px", "rgb(0, 0, 0)")),
            # arka plan zeminden farklı
            el(10, 0, "section", w=300, h=200, background_color="rgb(240, 240, 250)"),
            el(11, 10, "span", w=50, h=20, text=4),
            # header dışlanır
            el(12, 0, "header", w=300, h=200, background_color="rgb(0, 0, 0)"),
            el(13, 12, "span", w=50, h=20, text=4),
        ]
    )
    got = {e.idx: classify_element(e, s) for e in s.elements}
    assert got[1] is None and got[3] == "card" and got[5] is None
    assert got[7] is None and got[9] is None and got[10] == "card" and got[12] is None


def test_shadow_style_classification():
    def page(shadow):
        return snap(
            [
                el(0, None, "body", w=1440, h=900),
                el(1, 0, "div", w=300, h=200, box_shadow=shadow),
                el(2, 1, "p", w=100, h=20, text=10),
            ]
        )

    none = mine_components(page("none"), [])
    assert none.shadow_style == "none" and none.shadows == []
    assert mine_components(page("rgb(0, 0, 0) 4px 4px 0px 0px"), []).shadow_style == "hard"
    assert mine_components(page("rgba(0, 0, 0, 0.1) 0px 4px 6px -1px"), []).shadow_style == "soft"
    layered = "rgba(0, 0, 0, 0.1) 0px 1px 3px 0px, rgba(0, 0, 0, 0.06) 0px 1px 2px -1px"
    assert mine_components(page(layered), []).shadow_style == "layered"
    assert mine_components(page("rgba(0, 0, 0, 0) 0px 0px 0px 0px"), []).shadow_style == "none"


def test_neo_brutalist_style():
    black = "rgb(0, 0, 0)"
    hard = "rgb(0, 0, 0) 4px 4px 0px 0px"
    s = snap(
        [
            el(0, None, "body", w=1440, h=900),
            el(1, 0, "button", w=120, h=44, text=5, background_color="rgb(255, 230, 0)", box_shadow=hard, padding_top="12px", padding_right="24px", padding_bottom="12px", padding_left="24px", **border("3px", black)),
            el(2, 0, "button", w=120, h=44, text=5, background_color="rgb(255, 230, 0)", box_shadow=hard, padding_top="12px", padding_right="24px", padding_bottom="12px", padding_left="24px", **border("3px", black)),
            el(3, 0, "input", itype="text", w=200, h=40, background_color="rgb(255, 255, 255)", **border("3px", black)),
            el(4, 0, "div", w=300, h=200, background_color="rgb(255, 255, 255)", box_shadow=hard, **border("3px", black)),
            el(5, 4, "h3", w=100, h=20, text=6),
        ]
    )
    c = mine_components(s, [])
    assert c.shadow_style == "hard"
    b = c.button
    assert b is not None and b.border_width_px == 3 and b.border_color == "#000000"
    assert "4px 4px 0px" in b.box_shadow and b.border_radius_px == 0
    assert b.padding == (12, 24, 12, 24) and b.background == "#ffe600"
    assert b.stats.count == 2 and b.stats.with_border == 1 and b.stats.with_shadow == 1
    assert c.card is not None and c.card.border_width_px == 3
    assert c.input is not None and c.input.stats.with_shadow == 0


def test_glass_dark_style_and_radius_percent():
    s = snap(
        [
            el(0, None, "body", w=1440, h=900, background_color="rgb(10, 10, 15)"),
            el(
                1, 0, "div", w=300, h=200,
                background_color="rgba(255, 255, 255, 0.05)",
                backdrop_filter="blur(12px)",
                border_top_left_radius="8px", border_top_right_radius="8px",
                border_bottom_right_radius="8px", border_bottom_left_radius="8px",
                **border("1px", "rgba(255, 255, 255, 0.1)"),
            ),
            el(2, 1, "p", w=100, h=20, text=10),
            el(3, 0, "button", w=40, h=40, text=1, border_top_left_radius="50%", border_top_right_radius="50%", border_bottom_right_radius="50%", border_bottom_left_radius="50%"),
        ]
    )
    c = mine_components(s, [])
    assert c.card is not None
    assert c.card.border_radius_px == 8 and c.card.backdrop_filter == "blur(12px)"
    assert c.card.stats.with_backdrop == 1 and c.card.stats.with_background == 1
    assert c.card.border_color is not None and c.card.border_color != "#ffffff"
    assert c.button is not None and c.button.border_radius_px == 20
    assert c.shadow_style == "none"


def test_hover_merge():
    s = snap([el(0, None, "body", w=1440, h=900), el(1, 0, "button", w=100, h=40, text=3), el(2, 0, "button", w=100, h=40, text=3)])
    base = {"transform": "none", "background-color": "rgb(0, 0, 0)", "border-color": "rgb(0, 0, 0)", "box-shadow": "none"}

    def hd(after_t, changed, dur=150.0, easing="ease-out"):
        after = dict(base, transform=after_t)
        return HoverDiff(component_type="button", element_idx=1, selector="button", before=base, after=after, changed=changed, transition_duration_ms=dur, transition_easing=easing)

    hovers = [
        hd("matrix(1, 0, 0, 1, -2, -2)", ["transform", "box-shadow"]),
        hd("matrix(1, 0, 0, 1, -2, -2)", ["transform"]),
        hd("none", ["background-color"], dur=300.0, easing="ease"),
    ]
    c = mine_components(s, hovers)
    h = c.button.hover
    assert h is not None and h.samples == 3
    assert h.transform == "matrix(1, 0, 0, 1, -2, -2)"
    assert h.background_changes and h.shadow_changes and not h.border_changes
    assert h.duration_ms == 150.0 and h.easing == "ease-out"
    assert c.input is None and c.card is None


def test_sample_snapshot_and_determinism():
    s = RawSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    c = mine_components(s, [])
    assert c.button is not None and c.input is not None and c.card is not None
    assert c.button.stats.count >= 3 and c.input.stats.count == 3
    assert c.card.stats.count >= 3
    assert c.card.border_width_px == 1
    assert c.shadow_style in ("soft", "layered")
    assert c.model_dump_json() == mine_components(s, []).model_dump_json()
