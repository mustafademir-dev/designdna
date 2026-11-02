from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from designdna.generators import (
    OUTPUT_FILES, generate_all, render_design_md, render_preview_html, render_shadcn_theme,
    render_tailwind_v4, render_tokens_json, render_variables_css, write_blend_report,
)
from designdna.models import BlendReport, DesignSystem, RoleAssignment, SourceRef, SourceWeight

SAMPLE = Path(__file__).parent / "fixtures" / "sample_design_system.json"

SHADCN_VARS = [
    "background", "foreground", "card", "card-foreground", "popover", "popover-foreground",
    "primary", "primary-foreground", "secondary", "secondary-foreground", "muted", "muted-foreground",
    "accent", "accent-foreground", "destructive", "border", "input", "ring", "radius",
]


@pytest.fixture(scope="module")
def ds() -> DesignSystem:
    return DesignSystem.model_validate_json(SAMPLE.read_text(encoding="utf-8"))


def _validate_dtcg(node: dict, path: str = "") -> int:
    count = 0
    for key, val in node.items():
        assert not key.startswith("$"), path
        assert isinstance(val, dict), f"{path}/{key}"
        if "$value" in val:
            assert "$type" in val, f"{path}/{key} has no $type"
            t, v = val["$type"], val["$value"]
            if t == "color":
                assert re.fullmatch(r"#[0-9a-f]{6}([0-9a-f]{2})?", v)
            elif t == "dimension":
                assert re.fullmatch(r"-?\d+(\.\d+)?(px|em|rem)", v), v
            elif t == "duration":
                assert re.fullmatch(r"\d+(\.\d+)?ms", v)
            elif t == "cubicBezier":
                assert len(v) == 4 and all(isinstance(x, (int, float)) for x in v)
                assert 0 <= v[0] <= 1 and 0 <= v[2] <= 1
            elif t == "fontFamily":
                assert isinstance(v, list) and v and all(isinstance(x, str) for x in v)
            elif t == "fontWeight":
                assert isinstance(v, int)
            elif t == "number":
                assert isinstance(v, (int, float))
            elif t == "shadow":
                for layer in v if isinstance(v, list) else [v]:
                    assert {"color", "offsetX", "offsetY", "blur", "spread"} <= set(layer)
            else:
                raise AssertionError(f"unknown type {t}")
            count += 1
        else:
            count += _validate_dtcg(val, f"{path}/{key}")
    return count


def test_all_files_created(ds, tmp_path):
    paths = generate_all(ds, tmp_path / "out")
    assert [p.name for p in paths] == list(OUTPUT_FILES)
    for p in paths:
        assert p.exists() and p.stat().st_size > 100
        assert b"\r\n" not in p.read_bytes()


def test_deterministic(ds):
    for fn in (render_variables_css, render_tailwind_v4, render_shadcn_theme, render_tokens_json,
               render_design_md, render_preview_html):
        assert fn(ds) == fn(ds)


def test_tokens_dtcg(ds):
    tree = json.loads(render_tokens_json(ds))
    assert _validate_dtcg(tree) > 60
    for group in ("color", "font", "spacing", "radius", "shadow", "duration", "easing"):
        assert group in tree
    assert {"light", "dark"} == set(tree["color"])
    assert isinstance(tree["shadow"]["md"]["$value"], list) and len(tree["shadow"]["md"]["$value"]) == 2
    assert tree["shadow"]["sm"]["$value"]["offsetY"] == "1px"
    assert tree["easing"]["base"]["$value"] == [0.25, 0.1, 0.25, 1.0]


def test_tokens_cubic_bezier_and_none_shadow(ds):
    d = ds.model_copy(deep=True)
    d.motion.easing = "cubic-bezier(0.4, 0, 0.2, 1)"
    d.shadows.sm = "none"
    tree = json.loads(render_tokens_json(d))
    assert tree["easing"]["base"]["$value"] == [0.4, 0.0, 0.2, 1.0]
    assert "sm" not in tree["shadow"]
    _validate_dtcg(tree)


@pytest.mark.parametrize("block", [r":root", r"\.dark"])
def test_shadcn_vars_complete(ds, block):
    css = render_shadcn_theme(ds)
    m = re.search(block + r" \{(.*?)\n\}", css, re.S)
    assert m
    names = set(re.findall(r"--([\w-]+):", m.group(1)))
    assert set(SHADCN_VARS) <= names
    for name in SHADCN_VARS[:-1]:
        assert re.search(rf"--{name}: oklch\(", m.group(1))


def test_variables_css(ds):
    css = render_variables_css(ds)
    assert ":root {" in css and ".dark," in css and '[data-theme="dark"]' in css
    for token in ("--color-background", "--font-sans", "--radius-md", "--shadow-md", "--spacing-1", "--duration-base"):
        assert token in css


def test_tailwind(ds, tmp_path):
    cfg = generate_all(ds, tmp_path)[1]
    text = cfg.read_text(encoding="utf-8")
    assert "module.exports" in text and "theme:" in text and "extend:" in text
    assert text.count("{") == text.count("}") and text.count("[") == text.count("]")
    if shutil.which("node"):
        r = subprocess.run(["node", "--check", str(cfg)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    v4 = render_tailwind_v4(ds)
    assert "@theme {" in v4 and "--color-accent" in v4


def test_design_md_rules(ds):
    md = render_design_md(ds)
    assert len(md.splitlines()) <= 300
    rules = [l for l in md.splitlines() if l.startswith("- **Do") or l.startswith("- **Don't")]
    assert len(rules) >= 5
    for line in rules:
        assert "Evidence:" in line and re.search(r"\d", line.split("Evidence:")[1]), line
    assert "85%" not in md  # hiçbir kural uydurulmaz
    assert "shadows on inputs" in md  # with_shadow == 0 -> Don't


def test_design_md_missing_stats_no_rules(ds):
    d = ds.model_copy(deep=True)
    for c in (d.components.button, d.components.input, d.components.card):
        c.stats = None
        c.hover = None
    md = render_design_md(d)
    assert "sampled" not in md and "hover-probed" not in md


def test_design_md_many_sources(ds):
    d = ds.model_copy(deep=True)
    d.sources = [
        SourceRef(source=f"https://example.com/site-{i}", weight=1 / 80, natural_mode="light",
                  roles=["background", "surface", "text-primary", "accent"])
        for i in range(80)
    ]
    md = render_design_md(d)
    assert len(md.splitlines()) <= 300
    assert "more sources omitted" in md


def test_preview_self_contained(ds):
    html = render_preview_html(ds)
    assert not re.search(r"<script[^>]+src=", html)
    assert not re.search(r"<img\b", html)
    for sid in ("palette", "typography", "hero", "stats", "forms", "buttons", "theme-toggle"):
        assert f'id="{sid}"' in html
    assert "is-hover" in html and "disabled" in html


def test_blend_report(tmp_path):
    report = BlendReport(
        tool_version="0.1.0",
        sources=[SourceWeight(source="file:///a.html", input_weight=None, normalized_weight=1.0, eligible=True)],
        roles=[RoleAssignment(role="background", source="file:///a.html", reason="dominant")],
        counter_theme="derived",
        warnings=["w"],
    )
    p = write_blend_report(report, tmp_path / "x")
    assert p.name == "blend-report.json"
    assert BlendReport.model_validate_json(p.read_text(encoding="utf-8")) == report
