"""--source çözümleme testleri (tarayıcısız)."""

from __future__ import annotations

from pathlib import Path

import pytest

from designdna.errors import SourceParseError
from designdna.sources import is_capture_file, parse_source, source_to_path


def test_https_with_weight() -> None:
    s = parse_source("https://x.com@0.7")
    assert (s.location, s.weight, s.is_local) == ("https://x.com", 0.7, False)
    assert s.raw == "https://x.com@0.7"


def test_https_scope_without_weight() -> None:
    s = parse_source("https://example.com/@scope/pkg")
    assert s.location == "https://example.com/@scope/pkg"
    assert s.weight is None


def test_integer_weight_and_scope_with_weight() -> None:
    s = parse_source("https://example.com/@scope/pkg@2")
    assert s.location == "https://example.com/@scope/pkg"
    assert s.weight == 2.0


def test_file_uri_with_weight() -> None:
    s = parse_source("file:///C:/a.html@0.3")
    assert s.location == "file:///C:/a.html"
    assert s.weight == 0.3
    assert s.is_local


def test_windows_path_with_weight() -> None:
    s = parse_source(r"C:\yol\a.html@0.5")
    assert s.location == "file:///C:/yol/a.html"
    assert s.weight == 0.5 and s.is_local


def test_windows_path_with_at_no_weight() -> None:
    s = parse_source(r"C:\user@domain\a.html")
    assert s.location == "file:///C:/user@domain/a.html"
    assert s.weight is None


def test_windows_forward_slash_and_spaces() -> None:
    s = parse_source("D:/my dir/a.html")
    assert s.location == "file:///D:/my%20dir/a.html"


def test_relative_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    s = parse_source("./page.html@2")
    assert s.weight == 2.0
    assert s.is_local
    assert source_to_path(s) == (tmp_path / "page.html").resolve()


def test_posix_absolute_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "us@er" / "a b.html"
    s = parse_source(f"{p}@0.25")
    assert s.weight == 0.25
    assert "@" in s.location and " " not in s.location
    assert source_to_path(s) == p.resolve()


@pytest.mark.parametrize("text", ["https://x.com@0", "https://x.com@0.0", r"C:\a.html@0"])
def test_zero_weight_rejected(text: str) -> None:
    with pytest.raises(SourceParseError):
        parse_source(text)


def test_negative_is_not_a_weight() -> None:
    # '-1' regex'e uymaz; '@' konumun parçasıdır.
    s = parse_source("https://x.com@-1")
    assert s.weight is None and s.location == "https://x.com@-1"


def test_empty_rejected() -> None:
    with pytest.raises(SourceParseError):
        parse_source("   ")


def test_json_source_is_capture_file(tmp_path: Path) -> None:
    f = tmp_path / "site.capture.json"
    s = parse_source(f"{f}@0.4")
    assert s.is_local and s.weight == 0.4
    assert s.location.startswith("file://") and s.location.endswith("site.capture.json")
    assert is_capture_file(s)
    assert not is_capture_file(parse_source("https://x.com/data.json"))


def test_source_to_path_windows_drive() -> None:
    s = parse_source(r"C:\user@domain\a.html")
    path = source_to_path(s)
    assert path is not None
    assert path.as_posix() == "C:/user@domain/a.html"
    assert source_to_path(parse_source("https://x.com")) is None
