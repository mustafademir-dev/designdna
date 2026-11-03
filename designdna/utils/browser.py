"""Chromium bulma ve başlatma (Faz 0 kararı, bkz. DECISIONS.md).

Sıra: Playwright'ın kendi Chromium'u -> DESIGNDNA_CHROMIUM ortam değişkeni ->
PATH'teki chromium/chromium-browser/google-chrome -> bilinen kurulum yolları.
"""

from __future__ import annotations

import functools
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from designdna.errors import BrowserUnavailableError

if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import Browser, Playwright

_PATH_NAMES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome")

_KNOWN_PATHS = (
    Path("/opt/pw-browsers/chromium"),
    Path("/usr/bin/chromium"),
    Path("/usr/bin/chromium-browser"),
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
)


def find_chromium_executable() -> str | None:
    """Sistemde kullanılabilir bir Chromium/Chrome yürütülebilir dosyası arar."""
    env = os.environ.get("DESIGNDNA_CHROMIUM")
    if env and Path(env).exists():
        return env
    for name in _PATH_NAMES:
        found = shutil.which(name)
        if found:
            return found
    for candidate in _KNOWN_PATHS:
        if candidate.exists():
            return str(candidate)
    return None


def launch_chromium(playwright: "Playwright", **kwargs: Any) -> "Browser":
    """Headless Chromium başlatır; Playwright'ın kendi tarayıcısı yoksa sistemdekini dener."""
    from playwright.sync_api import Error as PlaywrightError

    kwargs.setdefault("headless", True)
    try:
        return playwright.chromium.launch(**kwargs)
    except PlaywrightError as first_error:
        executable = find_chromium_executable()
        if executable is None:
            raise BrowserUnavailableError(
                "Chromium bulunamadı. 'playwright install chromium' komutunu çalıştırın "
                "veya DESIGNDNA_CHROMIUM ortam değişkenine bir Chrome/Chromium yolu verin."
            ) from first_error
        try:
            return playwright.chromium.launch(executable_path=executable, **kwargs)
        except PlaywrightError as second_error:
            raise BrowserUnavailableError(
                f"Chromium başlatılamadı ({executable}): {second_error}"
            ) from second_error


@functools.lru_cache(maxsize=1)
def browser_available() -> bool:
    """Chromium bu makinede başlatılabiliyor mu? (Sonuç süreç boyunca önbelleklenir.)"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            browser.close()
        return True
    except Exception:
        return False
