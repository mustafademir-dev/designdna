"""tests/fixtures/*.html dosyalarından RawCapture JSON'ları üretir.

Kullanım: .venv/bin/python scripts/regen_fixture_snapshots.py
"""

from __future__ import annotations

from pathlib import Path

from designdna.extractor.dom_scanner import capture_source
from designdna.models import RawCapture

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
OUT_DIR = FIXTURES / "snapshots"


def _rewrite_source(capture: RawCapture, old: str, new: str) -> RawCapture:
    """Makineye bağlı file:// URI'sini kararlı bir kaynak adıyla değiştirir."""
    text = capture.model_dump_json().replace(old, new)
    return RawCapture.model_validate_json(text)


def main() -> None:
    from playwright.sync_api import sync_playwright

    from designdna.utils.browser import launch_chromium

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = launch_chromium(playwright)
        try:
            for html in sorted(FIXTURES.glob("*.html")):
                uri = html.resolve().as_uri()
                capture = capture_source(uri, browser=browser)
                capture = _rewrite_source(capture, uri, f"fixture://{html.name}")
                out = OUT_DIR / f"{html.stem}.capture.json"
                out.write_text(capture.model_dump_json(indent=2) + "\n", encoding="utf-8")
                print(f"yazıldı: {out}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
