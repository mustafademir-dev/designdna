"""Spacing ve layout madenciliği — saf Python."""

from __future__ import annotations

import re
from collections import Counter

from designdna.models import ElementRecord, Layout, RawSnapshot, Spacing

SCALE_4: tuple[float, ...] = (4, 8, 12, 16, 24, 32, 48, 64)
SCALE_8: tuple[float, ...] = (8, 16, 24, 32, 48, 64, 96)
#: IQR üst sınırının altına inmeyeceği taban (bölüm boşlukları meşru olarak büyük olabilir).
OUTLIER_FLOOR_PX = 128.0

_PX_RE = re.compile(r"^(-?(?:\d+\.?\d*|\.\d+))px$")
_SPACING_PROPS = (
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
    "row-gap",
    "column-gap",
)


def _px(value: str | None) -> float | None:
    if not value:
        return None
    m = _PX_RE.match(value.strip())
    return float(m.group(1)) if m else None


def _quantile(sorted_vals: list[float], q: float) -> float:
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def mine_spacing(snapshot: RawSnapshot) -> Spacing:
    values: list[float] = []
    for el in snapshot.elements:
        for prop in _SPACING_PROPS:
            v = _px(el.styles.get(prop))
            if v is not None and v > 0:
                values.append(round(v, 1))
    if not values:
        return Spacing(base=8, scale=list(SCALE_8), observed=[])
    values.sort()
    q1, q3 = _quantile(values, 0.25), _quantile(values, 0.75)
    upper = max(q3 + 1.5 * (q3 - q1), OUTLIER_FLOOR_PX)
    kept = [v for v in values if v <= upper]
    mult4 = [v for v in kept if abs(v / 4 - round(v / 4)) < 1e-6]
    not8 = [v for v in mult4 if abs(v / 8 - round(v / 8)) >= 1e-6]
    base = 4 if mult4 and len(not8) / len(mult4) >= 0.25 else 8
    scale = list(SCALE_4 if base == 4 else SCALE_8)
    return Spacing(base=base, scale=scale, observed=sorted(set(kept)))  # type: ignore[arg-type]


def _split_tracks(value: str) -> list[str]:
    tracks: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in value.strip():
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                tracks.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        tracks.append("".join(cur))
    return tracks


def count_grid_columns(value: str | None) -> int:
    """grid-template-columns iz sayısı; 'none'/boş -> 0."""
    if not value or value.strip().lower() in ("none", "normal"):
        return 0
    total = 0
    for tok in _split_tracks(value):
        m = re.match(r"^repeat\(\s*(\d+)\s*,", tok, re.IGNORECASE)
        if m:
            inner = tok[tok.index(",") + 1 : -1]
            total += int(m.group(1)) * max(1, len(_split_tracks(inner)))
        elif tok.lower().startswith("repeat("):
            total += 1
        elif tok.startswith("["):
            continue
        else:
            total += 1
    return total


def _ranked(counter: Counter, limit: int | None = None) -> list:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    keys = [k for k, _ in items]
    return keys[:limit] if limit else keys


def _container_width(elements: list[ElementRecord]) -> float | None:
    counter: Counter[float] = Counter()
    for el in elements:
        v = _px(el.styles.get("max-width"))
        if v is not None and v >= 600:
            counter[round(v, 1)] += 1
    if not counter:
        return None
    items = sorted(counter.items(), key=lambda kv: (-kv[1], -kv[0]))
    return items[0][0]


def mine_layout(desktop: RawSnapshot, mobile: RawSnapshot | None = None) -> Layout:
    grids: Counter[int] = Counter()
    flex: Counter[str] = Counter()
    for el in desktop.elements:
        display = el.styles.get("display", "")
        if display in ("grid", "inline-grid"):
            n = count_grid_columns(el.styles.get("grid-template-columns"))
            if n > 0:
                grids[n] += 1
        elif display in ("flex", "inline-flex"):
            jc = (el.styles.get("justify-content") or "normal").strip()
            ai = (el.styles.get("align-items") or "normal").strip()
            if jc == "normal" and ai == "normal":
                continue
            flex[f"{jc}/{ai}"] += 1
    bps: set[float] = set()
    for snap in (desktop, mobile):
        if snap is None:
            continue
        for mq in snap.media_queries:
            for w in (mq.min_width, mq.max_width):
                if w is not None and w > 0:
                    bps.add(float(w))
    return Layout(
        container_max_width=_container_width(desktop.elements),
        grid_columns=_ranked(grids),
        flex_alignments=_ranked(flex, 8),
        breakpoints=sorted(bps),
    )
