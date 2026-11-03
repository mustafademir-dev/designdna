from __future__ import annotations

import json
from pathlib import Path

from designdna.extractor.token_miner import classify_token, is_noise, mine_tokens
from designdna.models import CustomProperty, RawSnapshot

FIXTURE = Path(__file__).parent / "fixtures" / "sample_snapshot.json"


def _snap(props: list[tuple[str, str, str]]) -> RawSnapshot:
    base = json.loads(FIXTURE.read_text(encoding="utf-8"))
    base["custom_properties"] = [
        CustomProperty(name=n, value=v, selector=s).model_dump() for n, v, s in props
    ]
    return RawSnapshot.model_validate(base)


def test_is_noise():
    assert is_noise("--tw-ring-color")
    assert is_noise("--wp--preset--color--black")
    assert is_noise("--bs-blue")
    assert not is_noise("--primary")


def test_classify_kinds():
    assert classify_token("--primary", "#4f46e5") == "color"
    assert classify_token("--bg", "rgb(1, 2, 3)") == "color"
    assert classify_token("--space-4", "1rem") == "dimension"
    assert classify_token("--radius", "8px") == "radius"
    assert classify_token("--rounded-lg", "0.5rem") == "radius"
    assert classify_token("--font-sans", "Inter, sans-serif") == "font"
    assert classify_token("--shadow-md", "0 4px 6px -1px rgba(0,0,0,0.1)") == "shadow"
    assert classify_token("--elevation", "0 2px 4px rgba(0,0,0,0.2)") == "shadow"
    assert classify_token("--shadow-color", "#000") == "color"
    assert classify_token("--font-weight", "700") is None
    assert classify_token("--z-index", "10") is None
    assert classify_token("--x", "var(--y)") is None


def test_sample_snapshot_tokens():
    snap = RawSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    toks = mine_tokens(snap)
    names = [t.name for t in toks]
    assert "--primary" in names
    assert not any(n.startswith("--tw-") for n in names)
    kinds = {t.name: t.kind for t in toks}
    assert kinds["--radius"] == "radius"
    assert kinds["--font-sans"] == "font"
    assert kinds["--shadow-md"] == "shadow"
    # :root önce, [data-theme] sonra
    sels = [t.selector for t in toks]
    assert sels.index(":root") < sels.index('[data-theme="dark"]')
    assert mine_tokens(snap) == toks


def test_var_resolution_and_filtering():
    snap = _snap(
        [
            ("--brand", "#ff0000", ":root"),
            ("--accent", "var(--brand)", ":root"),
            ("--accent2", "var(--accent)", ":root"),
            ("--fallback", "var(--missing, #00ff00)", ":root"),
            ("--broken", "var(--missing)", ":root"),
            ("--loop-a", "var(--loop-b)", ":root"),
            ("--loop-b", "var(--loop-a)", ":root"),
            ("--garbage", "not a thing at all", ":root"),
            ("--btn", "#111", ".button"),
            ("--tw-x", "#222", ":root"),
            ("--dark-bg", "var(--brand)", '[data-theme="dark"]'),
            ("--brand", "#0000ff", '[data-theme="dark"]'),
            ("--b", "#333", "body"),
            ("--h", "#444", "html"),
        ]
    )
    toks = mine_tokens(snap)
    by = {(t.selector, t.name): t.value for t in toks}
    assert by[(":root", "--accent")] == "#ff0000"
    assert by[(":root", "--accent2")] == "#ff0000"
    assert by[(":root", "--fallback")] == "#00ff00"
    assert by[('[data-theme="dark"]', "--dark-bg")] == "#0000ff"
    names = {t.name for t in toks}
    assert not names & {"--broken", "--loop-a", "--loop-b", "--garbage", "--btn", "--tw-x"}
    order = [t.selector for t in toks]
    assert order == sorted(order, key=lambda s: [":root", "html", "body", '[data-theme="dark"]'].index(s))
