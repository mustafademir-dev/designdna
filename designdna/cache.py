"""Ham çıkarım önbelleği (CONTRACTS §3.3)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import ValidationError

from designdna import __version__ as TOOL_VERSION
from designdna.errors import DesignDNAError
from designdna.models import (
    DESKTOP_VIEWPORT,
    MOBILE_VIEWPORT,
    CacheEntry,
    RawCapture,
    RawSnapshot,
)

DEFAULT_CACHE_DIR = Path(".designdna") / "cache"

DESKTOP_KEY = f"{DESKTOP_VIEWPORT[0]}x{DESKTOP_VIEWPORT[1]}"
MOBILE_KEY = f"{MOBILE_VIEWPORT[0]}x{MOBILE_VIEWPORT[1]}"


def cache_key(url: str, viewport: str, color_scheme: str, tool_version: str = TOOL_VERSION) -> str:
    """sha256(url + viewport + color_scheme + tool_version) onaltılık özeti."""
    return hashlib.sha256((url + viewport + color_scheme + tool_version).encode("utf-8")).hexdigest()


def _viewport_str(snapshot: RawSnapshot) -> str:
    return f"{snapshot.viewport.width}x{snapshot.viewport.height}"


class CacheStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else Path.cwd() / DEFAULT_CACHE_DIR

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def _write(self, capture: RawCapture, snapshot: RawSnapshot, hovers: list) -> Path:
        viewport = _viewport_str(snapshot)
        key = cache_key(capture.source, viewport, snapshot.color_scheme, capture.tool_version)
        entry = CacheEntry(
            key=key,
            source=capture.source,
            viewport=viewport,
            color_scheme=snapshot.color_scheme,
            tool_version=capture.tool_version,
            snapshot=snapshot,
            hovers=hovers,
        )
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
        return path

    def _drop(self, source: str, viewport: str, color_scheme: str, versions: set[str]) -> None:
        for version in versions:
            self.path_for(cache_key(source, viewport, color_scheme, version)).unlink(missing_ok=True)

    def save_capture(self, capture: RawCapture) -> list[Path]:
        # Önceki taramadan kalan, yeni capture'da bulunmayan mobil/karşıt-mod girdilerini sil.
        versions = {capture.tool_version, TOOL_VERSION}
        if capture.mobile is None:
            self._drop(capture.source, MOBILE_KEY, "light", versions)
        if capture.counter is None:
            for scheme in ("dark", "light"):
                if scheme != capture.desktop.color_scheme:
                    self._drop(capture.source, DESKTOP_KEY, scheme, versions)
        paths = [self._write(capture, capture.desktop, capture.hovers)]
        if capture.mobile is not None:
            paths.append(self._write(capture, capture.mobile, []))
        if capture.counter is not None:
            paths.append(self._write(capture, capture.counter, []))
        return paths

    def _read(self, key: str) -> CacheEntry | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            return CacheEntry.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValidationError, ValueError, OSError):
            return None

    def load_capture(self, url: str) -> RawCapture | None:
        desktop = self._read(cache_key(url, DESKTOP_KEY, "light"))
        if desktop is None:
            return None
        mobile = self._read(cache_key(url, MOBILE_KEY, "light"))
        counter = self._read(cache_key(url, DESKTOP_KEY, "dark"))
        return RawCapture(
            tool_version=TOOL_VERSION,
            source=url,
            desktop=desktop.snapshot,
            mobile=mobile.snapshot if mobile else None,
            counter=counter.snapshot if counter else None,
            hovers=desktop.hovers,
        )

    def has(self, url: str) -> bool:
        return self.path_for(cache_key(url, DESKTOP_KEY, "light")).is_file()


def load_capture_file(path: Path) -> RawCapture:
    """Bir RawCapture JSON dosyasını okur."""
    path = Path(path)
    if not path.is_file():
        raise DesignDNAError(f"Çıkarım dosyası bulunamadı: {path}")
    try:
        return RawCapture.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as exc:
        raise DesignDNAError(f"Geçersiz çıkarım dosyası ({path}): {exc}") from exc
