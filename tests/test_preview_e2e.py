from __future__ import annotations

from pathlib import Path

import pytest

from designdna.generators import generate_all
from designdna.models import DesignSystem
from designdna.utils.browser import launch_chromium

SAMPLE = Path(__file__).parent / "fixtures" / "sample_design_system.json"

pytestmark = pytest.mark.browser


def test_preview_in_browser(tmp_path):
    from playwright.sync_api import sync_playwright

    ds = DesignSystem.model_validate_json(SAMPLE.read_text(encoding="utf-8"))
    preview = [p for p in generate_all(ds, tmp_path) if p.name == "preview.html"][0]
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = launch_chromium(pw)
        try:
            page = browser.new_page()
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(preview.as_uri())
            for sid in ("palette", "typography", "hero", "stats", "forms", "buttons"):
                assert page.locator(f"#{sid}").is_visible(), sid
            assert page.locator("#theme-toggle").is_visible()

            def state() -> tuple[bool, str]:
                return page.evaluate(
                    "[document.documentElement.classList.contains('dark'),"
                    " getComputedStyle(document.body).backgroundColor]"
                )

            dark0, bg0 = state()
            page.click("#theme-toggle")
            page.wait_for_timeout(400)  # background transition
            dark1, bg1 = state()
            assert dark1 != dark0 and bg1 != bg0
            page.click("#theme-toggle")
            page.wait_for_timeout(400)
            dark2, bg2 = state()
            assert dark2 == dark0 and bg2 == bg0
        finally:
            browser.close()
    assert errors == []
