"""hover_probe testleri (tarayıcı)."""

from __future__ import annotations

import json

import pytest

from designdna.extractor.dom_scanner import DESKTOP, load_page, scan_page
from designdna.extractor.hover_probe import (
    PROBE_STYLE_ATTR,
    parse_duration_ms,
    parse_easing,
    probe_hovers,
)

from conftest import EXPECTED_DIR, FIXTURE_NAMES, FIXTURES_DIR


def test_parse_duration_and_easing() -> None:
    assert parse_duration_ms("0.15s") == 150.0
    assert parse_duration_ms("200ms, 1s") == 200.0
    assert parse_duration_ms("0s") == 0.0
    assert parse_duration_ms("") == 0.0
    assert parse_easing("cubic-bezier(0.4, 0, 0.2, 1), ease") == "cubic-bezier(0.4, 0, 0.2, 1)"
    assert parse_easing("") == "ease"


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    from designdna.utils.browser import launch_chromium

    with sync_playwright() as p:
        b = launch_chromium(p)
        yield b
        b.close()


def _probe(browser, name: str, max_per_type: int = 5):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    page = ctx.new_page()
    uri = (FIXTURES_DIR / f"{name}.html").as_uri()
    load_page(page, uri)
    snap = scan_page(page, uri, DESKTOP, "light")
    hovers = probe_hovers(page, snap, max_per_type=max_per_type)
    return ctx, page, snap, hovers


@pytest.mark.browser
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_hover_expectations(browser, name: str) -> None:
    exp = json.loads((EXPECTED_DIR / f"{name}.json").read_text(encoding="utf-8"))["hover"]
    ctx, page, snap, hovers = _probe(browser, name)
    try:
        for kind in ("button", "input", "card"):
            assert sum(1 for h in hovers if h.component_type == kind) <= 5
        for kind, checks in exp.items():
            samples = [h for h in hovers if h.component_type == kind]
            assert samples, f"{kind} örneği yok"
            mapping = {
                "transform_changes": "transform",
                "background_changes": "background-color",
                "shadow_changes": "box-shadow",
            }
            for key, prop in mapping.items():
                want = checks.get(key)
                if want is None:
                    continue
                got = any(prop in h.changed for h in samples)
                assert got == want, f"{name}.{kind}.{key}"
        assert any(h.transition_duration_ms > 0 for h in hovers if h.component_type == "button")
        for h in hovers:
            assert set(h.before) == set(h.after) == {"transform", "background-color", "border-color", "box-shadow"}
            assert h.element_idx is not None
        # geçici stil kaldırıldı
        assert page.locator(f"style[{PROBE_STYLE_ATTR}]").count() == 0
    finally:
        ctx.close()


@pytest.mark.browser
def test_max_per_type_limits_samples(browser) -> None:
    ctx, page, snap, hovers = _probe(browser, "neo_brutalist", max_per_type=2)
    try:
        for kind in ("button", "input", "card"):
            assert sum(1 for h in hovers if h.component_type == kind) <= 2
        assert any(h.component_type == "button" for h in hovers)
    finally:
        ctx.close()


@pytest.mark.browser
def test_durations_in_ms(browser) -> None:
    ctx, page, snap, hovers = _probe(browser, "neo_brutalist")
    try:
        buttons = [h for h in hovers if h.component_type == "button"]
        assert buttons and all(h.transition_duration_ms == 150.0 for h in buttons)
        assert all(h.transition_easing == "ease" for h in buttons)
    finally:
        ctx.close()
