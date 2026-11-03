"""dom_scanner testleri: saf birim testleri, tarayıcı testleri ve commit'li snapshot testleri."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from designdna.cache import load_capture_file
from designdna.extractor.dom_scanner import (
    DESKTOP,
    TOOL_VERSION,
    capture_source,
    detect_natural_mode,
)
from designdna.models import BoundingBox, ElementRecord, RawCapture, Viewport
from designdna.utils.color_math import delta_e_ok, hex_to_rgb

from conftest import EXPECTED_DIR, FIXTURE_NAMES, FIXTURES_DIR, SNAPSHOTS_DIR


def _el(idx: int, bg: str, x=0.0, y=0.0, w=100.0, h=100.0, depth=1, in_vp=True) -> ElementRecord:
    return ElementRecord(
        idx=idx,
        parent_idx=None,
        depth=depth,
        tag="div",
        bbox=BoundingBox(x=x, y=y, width=w, height=h),
        area=w * h,
        in_viewport=in_vp,
        styles={"background-color": bg},
    )


def _expected(name: str) -> dict:
    return json.loads((EXPECTED_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _close(a: str, b: str, tol: float = 0.03) -> bool:
    return delta_e_ok(hex_to_rgb(a), hex_to_rgb(b)) <= tol


# ------------------------------------------------------------------ saf birim testleri


def test_detect_dark() -> None:
    mode, hx = detect_natural_mode([_el(0, "rgb(10, 10, 12)", w=1440, h=900)], DESKTOP)
    assert (mode, hx) == ("dark", "#0a0a0c")


def test_detect_light() -> None:
    mode, hx = detect_natural_mode([_el(0, "rgb(246, 249, 252)", w=1440, h=900)], DESKTOP)
    assert (mode, hx) == ("light", "#f6f9fc")


def test_transparent_body_with_wrapper() -> None:
    els = [
        _el(0, "rgba(0, 0, 0, 0)", w=1440, h=2000, depth=1),
        _el(1, "rgb(246, 249, 252)", w=1440, h=900, depth=2),
        _el(2, "rgb(255, 255, 255)", w=1440, h=70, depth=3),
    ]
    assert detect_natural_mode(els, DESKTOP) == ("light", "#f6f9fc")


def test_no_opaque_background_is_white() -> None:
    els = [_el(0, "rgba(0, 0, 0, 0)", w=1440, h=900), _el(1, "rgba(0, 0, 0, 0.5)", w=1440, h=900)]
    assert detect_natural_mode(els, DESKTOP) == ("light", "#ffffff")
    assert detect_natural_mode([], DESKTOP) == ("light", "#ffffff")


def test_ties_prefer_deeper_element() -> None:
    els = [_el(0, "rgb(255, 255, 255)", w=1440, h=900, depth=1), _el(1, "rgb(0, 0, 0)", w=1440, h=900, depth=2)]
    assert detect_natural_mode(els, DESKTOP) == ("dark", "#000000")


def test_ignores_out_of_viewport_and_uses_intersection() -> None:
    els = [
        _el(0, "rgb(0, 0, 0)", y=2000, w=1440, h=5000, in_vp=False),
        _el(1, "rgb(255, 255, 255)", y=0, w=500, h=500),
        # çok büyük ama viewport ile kesişimi küçük
        _el(2, "rgb(0, 0, 0)", y=880, w=1440, h=5000),
    ]
    assert detect_natural_mode(els, DESKTOP) == ("light", "#ffffff")


def test_viewport_model_helpers() -> None:
    assert (DESKTOP.width, DESKTOP.height) == (1440, 900)
    assert isinstance(Viewport(name="mobile", width=375, height=812), Viewport)


# ------------------------------------------------------------------ ortak beklenti kontrolü


def _check_expected(cap: RawCapture, exp: dict) -> None:
    d = cap.desktop
    assert d.natural_mode == exp["natural_mode"]
    assert _close(d.dominant_background, exp["dominant_background"])
    assert d.has_color_scheme_query == exp["has_color_scheme_query"]
    if exp["counter_background"] is None:
        assert cap.counter is None
    else:
        assert cap.counter is not None
        assert cap.counter.color_scheme == "dark"
        assert cap.counter.natural_mode != d.natural_mode
        assert _close(cap.counter.dominant_background, exp["counter_background"])
    ov = exp["overlays"]
    if ov.get("cookie_banner_removed"):
        assert d.removed_overlays
        assert not any(e.id == "cookie-banner" for e in d.elements)
    else:
        assert not d.removed_overlays
    if ov.get("header_position") is not None:
        headers = [e for e in d.elements if e.tag == "header"]
        assert headers and headers[0].styles["position"] == ov["header_position"]
    widths = {w for q in d.media_queries for w in (q.min_width, q.max_width) if w is not None}
    if cap.mobile is not None:
        widths |= {w for q in cap.mobile.media_queries for w in (q.min_width, q.max_width) if w is not None}
    for bp in exp["breakpoints_include"]:
        assert bp in widths
    assert len(d.gradients) >= exp["gradients_min"]
    tokens = {p.name for p in d.custom_properties}
    for name in exp["tokens"]["include"]:
        assert name in tokens


# ------------------------------------------------------------------ commit'li snapshot testleri (tarayıcısız)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_committed_snapshot_matches_expected(name: str) -> None:
    cap = load_capture_file(SNAPSHOTS_DIR / f"{name}.capture.json")
    assert cap.source == f"fixture://{name}.html"
    assert cap.desktop.source == cap.source and cap.tool_version == TOOL_VERSION
    assert cap.mobile is not None and (cap.mobile.viewport.width, cap.mobile.viewport.height) == (375, 812)
    assert (cap.desktop.viewport.width, cap.desktop.viewport.height) == (1440, 900)
    _check_expected(cap, _expected(name))


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_committed_snapshot_has_raw_tw_vars_and_idx(name: str) -> None:
    cap = load_capture_file(SNAPSHOTS_DIR / f"{name}.capture.json")
    assert [e.idx for e in cap.desktop.elements] == list(range(len(cap.desktop.elements)))
    if name == "linear_dark":
        assert any(p.name.startswith("--tw-") for p in cap.desktop.custom_properties)


# ------------------------------------------------------------------ tarayıcı testleri


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    from designdna.utils.browser import launch_chromium

    with sync_playwright() as p:
        b = launch_chromium(p)
        yield b
        b.close()


@pytest.fixture(scope="module")
def captures(browser):
    cache: dict[str, RawCapture] = {}

    def get(name: str) -> RawCapture:
        if name not in cache:
            cache[name] = capture_source((FIXTURES_DIR / f"{name}.html").as_uri(), browser=browser)
        return cache[name]

    return get


@pytest.mark.browser
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_scan_fixture_matches_expected(name: str, captures) -> None:
    cap = captures(name)
    _check_expected(cap, _expected(name))
    assert cap.mobile is not None
    assert (cap.mobile.viewport.width, cap.mobile.viewport.height) == (375, 812)
    assert cap.mobile.color_scheme == "light"


@pytest.mark.browser
def test_scan_matches_committed_snapshot(captures) -> None:
    cap = captures("neo_brutalist")
    stored = load_capture_file(SNAPSHOTS_DIR / "neo_brutalist.capture.json")
    assert len(cap.desktop.elements) == len(stored.desktop.elements)
    assert cap.desktop.dominant_background == stored.desktop.dominant_background


@pytest.mark.browser
def test_tw_vars_raw_and_text_not_copied(captures) -> None:
    cap = captures("linear_dark")
    assert any(p.name.startswith("--tw-") for p in cap.desktop.custom_properties)
    assert all(e.text_length >= 0 for e in cap.desktop.elements)
    by_tag = [e for e in cap.desktop.elements if e.tag in ("h1", "p")]
    assert by_tag and all(e.text_length > 0 for e in by_tag)
    assert any(e.text_length > 0 for e in cap.desktop.elements)
    for e in cap.desktop.elements:
        assert not ({"text", "inner_text", "text_content"} & set(e.model_dump()))
    assert "html" == cap.desktop.elements[0].tag and cap.desktop.elements[0].parent_idx is None


@pytest.mark.browser
def test_visibility_filter_and_idx_attributes(browser, tmp_path) -> None:
    html = (
        "<html><body style='margin:0'>"
        "<div id='a' style='width:50px;height:50px;background:#fff'>x</div>"
        "<div id='b' style='display:none;width:50px;height:50px'>x</div>"
        "<div id='c' style='visibility:hidden;width:50px;height:50px'>x</div>"
        "<div id='d' style='opacity:0;width:50px;height:50px'>x</div>"
        "<div id='e' style='width:1px;height:50px;background:red'></div>"
        "<div id='f' style='width:50px;height:50px;background:red'><div id='cookie-x' style='width:20px;height:20px'></div></div>"
        "</body></html>"
    )
    from designdna.extractor.dom_scanner import load_page, scan_page

    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = ctx.new_page()
        f = tmp_path / "t.html"
        f.write_text(html, encoding="utf-8")
        load_page(page, f.as_uri())
        snap = scan_page(page, "data:test", DESKTOP, "light")
        ids = {e.id for e in snap.elements}
        assert {"a", "f"} <= ids
        assert not ids & {"b", "c", "d", "e"}
        assert snap.removed_overlays == ["div#cookie-x"]
        for e in snap.elements:
            assert page.locator(f'[data-designdna-idx="{e.idx}"]').count() == 1
    finally:
        ctx.close()


@pytest.mark.browser
def test_cookie_check_does_not_hide_wrapper_or_header(browser, tmp_path) -> None:
    html = (
        "<html><body>"
        "<div id='wrap'><header id='h' style='position:fixed;top:0;left:0;width:100%;height:600px;background:#eee'>hi</header>"
        "<div id='big'>" + "lorem " * 200 + "cookie</div>"
        "<p id='tiny' style='position:fixed;bottom:0'>We use cookies</p></div></body></html>"
    )
    from designdna.extractor.dom_scanner import load_page, scan_page

    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = ctx.new_page()
        f = tmp_path / "t.html"
        f.write_text(html, encoding="utf-8")
        load_page(page, f.as_uri())
        snap = scan_page(page, "data:test", DESKTOP, "light")
        ids = {e.id for e in snap.elements}
        assert {"wrap", "h", "big"} <= ids
        assert "tiny" not in ids
    finally:
        ctx.close()


def _scan_html(browser, tmp_path, html: str):
    from designdna.extractor.dom_scanner import load_page, scan_page

    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = ctx.new_page()
        f = tmp_path / "t.html"
        f.write_text(html, encoding="utf-8")
        load_page(page, f.as_uri())
        return scan_page(page, "data:test", DESKTOP, "light")
    finally:
        ctx.close()


@pytest.mark.browser
def test_opacity_zero_ancestor_hides_subtree(browser, tmp_path) -> None:
    html = (
        "<html><body style='margin:0'>"
        "<div id='p' style='opacity:0;width:100px;height:100px'>"
        "<div id='kid' style='width:50px;height:50px;background:red'><span id='gk'>x</span></div></div>"
        "<div id='vh' style='visibility:hidden;width:100px;height:100px'>"
        "<div id='vis' style='visibility:visible;width:50px;height:50px'>y</div></div>"
        "<div id='ok' style='width:50px;height:50px'>z</div></body></html>"
    )
    ids = {e.id for e in _scan_html(browser, tmp_path, html).elements}
    assert not ids & {"p", "kid", "gk", "vh"}
    assert {"ok", "vis"} <= ids


@pytest.mark.browser
def test_cookie_wrapper_class_not_hidden_but_fixed_banner_is(browser, tmp_path) -> None:
    html = (
        "<html><body style='margin:0'>"
        "<div id='plain' class='gdpr-wrap' style='width:1440px;height:800px'>filler</div>"
        "<div id='page' class='cookie-consent-open' style='min-height:900px'><h1>Title</h1><p>body</p></div>"
        "<div id='banner' class='cookie-banner' style='position:fixed;bottom:0;left:0;width:300px;height:60px'>We use cookies</div>"
        "</body></html>"
    )
    snap = _scan_html(browser, tmp_path, html)
    ids = {e.id for e in snap.elements}
    assert {"page", "plain"} <= ids
    assert "banner" not in ids
    assert snap.removed_overlays == ["div#banner.cookie-banner"]


@pytest.mark.browser
def test_scroll_loop_respects_10000px_cap(browser, tmp_path) -> None:
    import time

    from designdna.extractor.dom_scanner import _SCROLL_JS, load_page

    f = tmp_path / "tall.html"
    f.write_text("<html><body style='margin:0'><div style='height:50000px'>x</div></body></html>", encoding="utf-8")
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        page = ctx.new_page()
        t0 = time.monotonic()
        load_page(page, f.as_uri())
        assert time.monotonic() - t0 < 15
        max_y = page.evaluate(_SCROLL_JS, 10000)
        assert 0 < max_y <= 10000
        assert page.evaluate("window.scrollY") == 0
    finally:
        ctx.close()
