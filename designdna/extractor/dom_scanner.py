"""Tarayıcı tabanlı DOM tarayıcısı (CONTRACTS §3.1).

Tüm DOM/stil okuması tek bir ``page.evaluate()`` içinde ``js/scan.js`` ile yapılır.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from designdna import __version__
from designdna.errors import DesignDNAError
from designdna.models import (
    DESKTOP_VIEWPORT,
    MOBILE_VIEWPORT,
    STYLE_PROPERTIES,
    ColorScheme,
    ElementRecord,
    RawCapture,
    RawSnapshot,
    ThemeMode,
    Viewport,
)
from designdna.utils.color_math import parse_color, rgb_to_hex, rgb_to_oklch

if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import Browser, Page

TOOL_VERSION = __version__

_SCAN_JS_PATH = Path(__file__).resolve().parent / "js" / "scan.js"

_SCROLL_JS = """
async (maxPx) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const step = Math.max(300, Math.floor(window.innerHeight * 0.8));
  let y = 0;
  let maxY = 0;
  for (let i = 0; i < 40; i++) {
    const limit = Math.min(document.documentElement.scrollHeight, maxPx);
    if (y >= limit) break;
    y = Math.min(y + step, limit);
    window.scrollTo(0, y);
    maxY = Math.max(maxY, y);
    await sleep(25);
  }
  window.scrollTo(0, 0);
  await sleep(100);
  return maxY;
}
"""

DESKTOP = Viewport(name="desktop", width=DESKTOP_VIEWPORT[0], height=DESKTOP_VIEWPORT[1])
MOBILE = Viewport(name="mobile", width=MOBILE_VIEWPORT[0], height=MOBILE_VIEWPORT[1])


def _scan_script() -> str:
    return _SCAN_JS_PATH.read_text(encoding="utf-8")


def detect_natural_mode(elements: list[ElementRecord], viewport: Viewport) -> tuple[ThemeMode, str]:
    """Viewport'ta en büyük alanı kaplayan opak arka plana göre doğal modu bulur (saf)."""
    best: tuple[float, int, int] | None = None
    best_hex = "#ffffff"
    for el in elements:
        if not el.in_viewport:
            continue
        rgba = parse_color(el.styles.get("background-color", ""))
        if rgba is None or rgba[3] < 1.0:
            continue
        b = el.bbox
        ix = max(0.0, min(b.x + b.width, viewport.width) - max(b.x, 0.0))
        iy = max(0.0, min(b.y + b.height, viewport.height) - max(b.y, 0.0))
        area = ix * iy
        if area <= 0:
            continue
        key = (area, el.depth, -el.idx)
        if best is None or key > best:
            best = key
            best_hex = rgb_to_hex((rgba[0], rgba[1], rgba[2]))
    rgb = parse_color(best_hex)
    assert rgb is not None
    lightness = rgb_to_oklch((rgb[0], rgb[1], rgb[2]))[0]
    return ("dark" if lightness < 0.5 else "light"), best_hex


def load_page(page: "Page", url: str) -> None:
    """Sayfayı yükler, fontları bekler, lazy-load için scroll edip en üste döner."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except PlaywrightError as exc:
        raise DesignDNAError(f"Sayfa açılamadı ({url}): {exc}") from exc
    try:
        page.wait_for_load_state("networkidle", timeout=3000)
    except PlaywrightTimeout:
        pass
    try:
        page.evaluate("document.fonts.ready.then(() => true)")
        page.evaluate(_SCROLL_JS, 10000)
        page.evaluate("document.fonts.ready.then(() => true)")
    except PlaywrightError as exc:
        raise DesignDNAError(f"Sayfa hazırlanırken hata oluştu ({url}): {exc}") from exc


def scan_page(page: "Page", source: str, viewport: Viewport, color_scheme: ColorScheme) -> RawSnapshot:
    """Yüklenmiş sayfayı tek ``page.evaluate`` ile tarar ve RawSnapshot döndürür."""
    from playwright.sync_api import Error as PlaywrightError

    opts: dict[str, Any] = {
        "viewport": {"width": viewport.width, "height": viewport.height},
        "properties": list(STYLE_PROPERTIES),
    }
    try:
        raw = page.evaluate(_scan_script(), opts)
    except PlaywrightError as exc:
        raise DesignDNAError(f"Sayfa taranamadı ({source}): {exc}") from exc

    elements = [ElementRecord.model_validate(e) for e in raw["elements"]]
    mode, dominant = detect_natural_mode(elements, viewport)
    return RawSnapshot(
        tool_version=TOOL_VERSION,
        source=source,
        viewport=viewport,
        color_scheme=color_scheme,
        natural_mode=mode,
        dominant_background=dominant,
        page_height=raw["page_height"],
        elements=elements,
        custom_properties=raw["custom_properties"],
        font_faces=raw["font_faces"],
        font_links=raw["font_links"],
        media_queries=raw["media_queries"],
        gradients=raw["gradients"],
        has_color_scheme_query=raw["has_color_scheme_query"],
        removed_overlays=raw["removed_overlays"],
    )


def _scan_in_context(
    browser: "Browser", url: str, viewport: Viewport, color_scheme: ColorScheme, hover: bool = False
) -> tuple[RawSnapshot, list]:
    context = browser.new_context(
        viewport={"width": viewport.width, "height": viewport.height},
        color_scheme=color_scheme,
        device_scale_factor=1,
    )
    try:
        page = context.new_page()
        load_page(page, url)
        snapshot = scan_page(page, url, viewport, color_scheme)
        hovers: list = []
        if hover:
            from designdna.extractor.hover_probe import probe_hovers

            hovers = probe_hovers(page, snapshot)
        return snapshot, hovers
    finally:
        context.close()


def _capture(browser: "Browser", url: str) -> RawCapture:
    desktop, hovers = _scan_in_context(browser, url, DESKTOP, "light", hover=True)
    mobile, _ = _scan_in_context(browser, url, MOBILE, "light")
    counter = None
    if desktop.has_color_scheme_query:
        other: ColorScheme = "dark"
        candidate, _ = _scan_in_context(browser, url, DESKTOP, other)
        if candidate.natural_mode != desktop.natural_mode:
            counter = candidate
    return RawCapture(
        tool_version=TOOL_VERSION,
        source=url,
        desktop=desktop,
        mobile=mobile,
        counter=counter,
        hovers=hovers,
    )


def capture_source(url: str, *, browser: "Browser | None" = None) -> RawCapture:
    """Bir kaynağın desktop + hover + mobile (+ karşı tema) ham çıkarımını yapar."""
    if browser is not None:
        return _capture(browser, url)

    from playwright.sync_api import sync_playwright

    from designdna.utils.browser import launch_chromium

    with sync_playwright() as playwright:
        own = launch_chromium(playwright)
        try:
            return _capture(own, url)
        finally:
            own.close()
