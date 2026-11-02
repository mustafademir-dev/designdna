"""`--source` argümanlarının çözümlenmesi (CONTRACTS §6)."""

from __future__ import annotations

import os
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlparse
from urllib.parse import quote

from designdna.errors import SourceParseError
from designdna.models import SourceSpec

WEIGHT_RE = re.compile(r"@(\d+(?:\.\d+)?)$")
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
_DRIVE_URI_PATH_RE = re.compile(r"^/[A-Za-z]:/")
_URI_SAFE = "/:@"


def _file_uri(posix_path: str) -> str:
    """Deterministik file URI; `@` okunabilirlik için kodlanmaz."""
    if not posix_path.startswith("/"):
        posix_path = "/" + posix_path  # 'C:/x' -> '/C:/x'
    return "file://" + quote(posix_path, safe=_URI_SAFE)


def parse_source(text: str) -> SourceSpec:
    """`konum[@ağırlık]` değerini SourceSpec'e çevirir."""
    raw = text
    value = text.strip()
    if not value:
        raise SourceParseError("Boş kaynak verildi. Örnek: --source \"https://site.com@0.7\"")

    weight: float | None = None
    match = WEIGHT_RE.search(value)
    # '@0' / '@0.0' pozitif sayı değildir: '@' konumun parçası kalır (spec §6, D20).
    if match and float(match.group(1)) > 0:
        weight = float(match.group(1))
        value = value[: match.start()]
        if not value:
            raise SourceParseError(f"Kaynak konumu eksik: '{raw}'")

    lowered = value.lower()
    if lowered.startswith(("http://", "https://")):
        location, is_local = value, False
    elif lowered.startswith("file://"):
        location, is_local = value, True
    elif _WINDOWS_PATH_RE.match(value):
        location, is_local = _file_uri(PureWindowsPath(value).as_posix()), True
    else:
        resolved = Path(value).expanduser().resolve()
        location, is_local = _file_uri(resolved.as_posix()), True

    return SourceSpec(raw=raw, location=location, weight=weight, is_local=is_local)


def display_source(location: str) -> str:
    """Gösterim adı: file://…/a.html -> a.html, fixture://a.html -> a.html; http(s) olduğu gibi."""
    lowered = location.lower()
    if lowered.startswith("fixture://"):
        return location[len("fixture://"):] or location
    if lowered.startswith("file://"):
        name = unquote(urlparse(location).path).rstrip("/").rsplit("/", 1)[-1]
        return name or location
    return location


def source_to_path(spec: SourceSpec) -> Path | None:
    """file:// kaynağının yerel yolu; uzak kaynaklarda None."""
    if not spec.is_local:
        return None
    parsed = urlparse(spec.location)
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc.lower() != "localhost":
        path = f"//{parsed.netloc}{path}"  # UNC
    if _DRIVE_URI_PATH_RE.match(path):
        return Path(path[1:])
    if os.name == "nt" and path.startswith("//"):
        return Path(path.replace("/", "\\"))
    return Path(path)


def is_capture_file(spec: SourceSpec) -> bool:
    """Kaynak hazır bir RawCapture .json dosyası mı?"""
    return spec.is_local and urlparse(spec.location).path.lower().endswith(".json")
