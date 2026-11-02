"""Ortak test yardımcıları. Tüm testler offline çalışır."""

from __future__ import annotations

from pathlib import Path

import pytest

from designdna.utils.browser import browser_available

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
EXPECTED_DIR = TESTS_DIR / "expected"
SNAPSHOTS_DIR = FIXTURES_DIR / "snapshots"

FIXTURE_NAMES = ("neo_brutalist", "linear_dark", "stripe_clean")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """`@pytest.mark.browser` testlerini Chromium yoksa gerekçeyle atlar."""
    if not any(item.get_closest_marker("browser") for item in items):
        return
    if browser_available():
        return
    skip = pytest.mark.skip(reason="Chromium bulunamadı; tarayıcı testleri atlandı (bkz. TODO.md)")
    for item in items:
        if item.get_closest_marker("browser"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def expected_dir() -> Path:
    return EXPECTED_DIR


@pytest.fixture(scope="session")
def snapshots_dir() -> Path:
    return SNAPSHOTS_DIR
