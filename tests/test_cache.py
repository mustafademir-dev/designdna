"""cache testleri (tarayıcısız)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from designdna import __version__
from designdna.cache import (
    DEFAULT_CACHE_DIR,
    CacheStore,
    cache_key,
    load_capture_file,
)
from designdna.errors import DesignDNAError
from designdna.models import CacheEntry

from conftest import FIXTURE_NAMES, SNAPSHOTS_DIR


def _capture(name: str = "stripe_clean"):
    return load_capture_file(SNAPSHOTS_DIR / f"{name}.capture.json")


def test_cache_key_formula() -> None:
    expected = hashlib.sha256(f"http://x1440x900light{__version__}".encode("utf-8")).hexdigest()
    assert cache_key("http://x", "1440x900", "light") == hashlib.sha256(
        f"http://x1440x900light{__version__}".encode("utf-8")
    ).hexdigest()
    assert cache_key("http://x", "1440x900", "light", __version__) == expected
    assert cache_key("http://x", "1440x900", "light", "9.9") != expected
    assert cache_key("http://x", "1440x900", "dark") != expected
    assert cache_key("http://x", "375x812", "light") != expected


def test_default_dir_and_store_root(tmp_path: Path) -> None:
    assert DEFAULT_CACHE_DIR == Path(".designdna") / "cache"
    store = CacheStore(tmp_path)
    key = cache_key("u", "1440x900", "light")
    assert store.path_for(key) == tmp_path / f"{key}.json"
    assert CacheStore().root == Path.cwd() / DEFAULT_CACHE_DIR


def test_roundtrip_with_mobile_and_counter(tmp_path: Path) -> None:
    cap = _capture("stripe_clean")
    assert cap.mobile is not None and cap.counter is not None and cap.hovers
    store = CacheStore(tmp_path)
    assert not store.has(cap.source)
    paths = store.save_capture(cap)
    assert len(paths) == 3 and all(p.is_file() and p.parent == tmp_path for p in paths)
    assert store.has(cap.source)
    entry = CacheEntry.model_validate_json(paths[0].read_text(encoding="utf-8"))
    assert entry.key == paths[0].stem == cache_key(cap.source, "1440x900", "light")
    loaded = store.load_capture(cap.source)
    assert loaded is not None
    assert loaded.model_dump() == cap.model_dump()


def test_roundtrip_without_counter_or_mobile(tmp_path: Path) -> None:
    cap = _capture("neo_brutalist")
    assert cap.counter is None
    store = CacheStore(tmp_path)
    assert len(store.save_capture(cap)) == 2
    loaded = store.load_capture(cap.source)
    assert loaded is not None and loaded.counter is None and loaded.mobile is not None
    only_desktop = cap.model_copy(update={"mobile": None})
    other = CacheStore(tmp_path / "b")
    assert len(other.save_capture(only_desktop)) == 1
    again = other.load_capture(cap.source)
    assert again is not None and again.mobile is None


def test_refresh_without_counter_or_mobile_removes_stale(tmp_path: Path) -> None:
    full = _capture("stripe_clean")
    assert full.mobile is not None and full.counter is not None
    store = CacheStore(tmp_path)
    store.save_capture(full)
    refreshed = full.model_copy(update={"counter": None, "mobile": None})
    store.save_capture(refreshed)
    loaded = store.load_capture(full.source)
    assert loaded is not None and loaded.counter is None and loaded.mobile is None
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_missing_returns_none(tmp_path: Path) -> None:
    store = CacheStore(tmp_path / "nope")
    assert store.load_capture("file:///x.html") is None
    assert not store.has("file:///x.html")


def test_corrupt_entry_returns_none(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    store.path_for(cache_key("u", "1440x900", "light")).write_text("{bozuk", encoding="utf-8")
    assert store.load_capture("u") is None


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_load_capture_file(name: str) -> None:
    cap = load_capture_file(SNAPSHOTS_DIR / f"{name}.capture.json")
    assert cap.source == f"fixture://{name}.html"


def test_load_capture_file_errors(tmp_path: Path) -> None:
    with pytest.raises(DesignDNAError):
        load_capture_file(tmp_path / "yok.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(DesignDNAError):
        load_capture_file(bad)
