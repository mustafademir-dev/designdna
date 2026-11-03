from __future__ import annotations

import json
from pathlib import Path

from designdna.extractor.layout_miner import count_grid_columns, mine_layout, mine_spacing
from designdna.models import STYLE_PROPERTIES, RawSnapshot

FIXTURE = Path(__file__).parent / "fixtures" / "sample_snapshot.json"
DEFAULTS = {p: "0px" for p in STYLE_PROPERTIES}
DEFAULTS.update(
    {
        "color": "rgb(0, 0, 0)",
        "background-color": "rgba(0, 0, 0, 0)",
        "box-shadow": "none",
        "display": "block",
        "max-width": "none",
        "grid-template-columns": "none",
        "justify-content": "normal",
        "align-items": "normal",
    }
)


def make_snapshot(specs: list[dict[str, str]], media=None) -> RawSnapshot:
    elements = []
    for i, st in enumerate(specs):
        styles = dict(DEFAULTS)
        styles.update(st)
        elements.append(
            {
                "idx": i,
                "parent_idx": None if i == 0 else 0,
                "depth": 0 if i == 0 else 1,
                "tag": "div",
                "bbox": {"x": 0, "y": 0, "width": 100, "height": 100},
                "area": 10000,
                "in_viewport": True,
                "styles": styles,
            }
        )
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
            "media_queries": media or [],
        }
    )


def test_spacing_base_8():
    snap = make_snapshot([{"padding-top": "16px", "margin-bottom": "24px", "row-gap": "8px"}] * 5 + [{"padding-left": "32px"}])
    sp = mine_spacing(snap)
    assert sp.base == 8
    assert sp.scale == [8, 16, 24, 32, 48, 64, 96]
    assert sp.observed == [8, 16, 24, 32]


def test_spacing_base_4():
    snap = make_snapshot([{"padding-top": "12px", "padding-left": "20px", "margin-top": "4px", "column-gap": "8px"}] * 4)
    sp = mine_spacing(snap)
    assert sp.base == 4
    assert sp.scale == [4, 8, 12, 16, 24, 32, 48, 64]


def test_spacing_outliers_and_auto():
    specs = [{"padding-top": "8px", "padding-bottom": "16px", "margin-left": "auto"}] * 10
    specs.append({"margin-left": "480px"})
    specs.append({"margin-left": "-12px"})
    sp = mine_spacing(make_snapshot(specs))
    assert 480 not in sp.observed
    assert 12 not in sp.observed
    assert sp.base == 8


def test_spacing_empty():
    sp = mine_spacing(make_snapshot([{}]))
    assert sp.base == 8 and sp.observed == []


def test_grid_column_counts():
    assert count_grid_columns("300px 300px 300px") == 3
    assert count_grid_columns("none") == 0
    assert count_grid_columns("repeat(4, 1fr)") == 4
    assert count_grid_columns("repeat(2, 100px 200px)") == 4
    assert count_grid_columns("minmax(0px, 1fr) minmax(10px, 20px)") == 2
    assert count_grid_columns("[a] 100px [b] 200px") == 2


def test_container_grid_flex_breakpoints():
    desktop = make_snapshot(
        [
            {"max-width": "1200px"},
            {"max-width": "1200px"},
            {"max-width": "480px"},
            {"max-width": "720px"},
            {"display": "grid", "grid-template-columns": "368px 368px 368px"},
            {"display": "grid", "grid-template-columns": "264px 264px 264px 264px"},
            {"display": "grid", "grid-template-columns": "1px 1px 1px"},
            {"display": "flex", "justify-content": "space-between", "align-items": "center"},
            {"display": "flex", "justify-content": "space-between", "align-items": "center"},
            {"display": "flex", "justify-content": "normal", "align-items": "normal"},
        ],
        media=[
            {"condition": "(min-width: 1024px)", "min_width": 1024},
            {"condition": "(max-width: 768px)", "max_width": 768},
            {"condition": "(prefers-color-scheme: dark)", "prefers_color_scheme": "dark"},
        ],
    )
    mobile = make_snapshot([{}], media=[{"condition": "(min-width: 640px)", "min_width": 640}, {"condition": "(max-width: 768px)", "max_width": 768}])
    lay = mine_layout(desktop, mobile)
    assert lay.container_max_width == 1200
    assert lay.grid_columns == [3, 4]
    assert lay.flex_alignments == ["space-between/center"]
    assert lay.breakpoints == [640, 768, 1024]


def test_sample_snapshot():
    snap = RawSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    lay = mine_layout(snap)
    assert lay.container_max_width == 1200
    assert set(lay.grid_columns) >= {3, 4}
    assert lay.breakpoints == [768, 1024]
    sp = mine_spacing(snap)
    assert sp.base in (4, 8)
    assert mine_spacing(snap) == sp
