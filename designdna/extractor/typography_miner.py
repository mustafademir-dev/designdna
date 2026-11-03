"""Tipografi madenciliği: RawSnapshot -> Typography (saf Python, tarayıcısız). Bkz. CONTRACTS.md §3.7."""

from __future__ import annotations

import re
import statistics
from collections import defaultdict

from designdna.models import ElementRecord, FontUsage, RawSnapshot, TypeStyle, Typography

TYPE_SCALE_RATIOS = (1.125, 1.2, 1.25, 1.333, 1.414, 1.5, 1.618)
MONO_HINTS = ("mono", "code", "courier", "consolas", "menlo", "monaco")

_STYLE_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "small", "code", "button")
_BODY_TAGS = ("p", "li", "span", "div")
_DISPLAY_TAGS = ("h1", "h2", "h3")
_MONO_TAGS = ("code", "pre", "kbd", "samp")
_GENERIC_MONO = ("monospace", "ui-monospace")
_KNOWN_NON_MONO = (
    "sans-serif", "serif", "system-ui", "ui-sans-serif", "ui-serif", "-apple-system", "blinkmacsystemfont",
    "inter", "arial", "helvetica", "helvetica neue", "roboto", "georgia", "times", "times new roman",
    "segoe ui", "open sans", "lato", "poppins", "montserrat", "verdana", "tahoma", "cursive", "fantasy",
)


def _split_stack(stack: str) -> list[str]:
    items: list[str] = []
    cur: list[str] = []
    quote = ""
    for ch in stack:
        if quote:
            if ch == quote:
                quote = ""
            cur.append(ch)
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch == ",":
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    items.append("".join(cur))
    return [i.strip().strip("\"'").strip() for i in items if i.strip()]


def primary_family(stack: str) -> str:
    """Fallback zincirinin ilk ailesi, tırnaksız ('monospace'/'sans-serif' generic ise o)."""
    items = _split_stack(stack or "")
    return items[0] if items else ""


def is_monospace(stack: str) -> bool:
    items = _split_stack(stack or "")
    if not items:
        return False
    primary = items[0].lower()
    if any(h in primary for h in MONO_HINTS):
        return True
    has_generic = any(i.lower() in _GENERIC_MONO for i in items)
    return has_generic and primary not in _KNOWN_NON_MONO


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    m = re.match(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+))\s*([a-z%]*)\s*$", value.strip().lower())
    if not m:
        return None
    return float(m.group(1))


def _size(el: ElementRecord) -> float | None:
    v = _num(el.styles.get("font-size"))
    return v if v is not None and v > 0 else None


def _line_height(raw: str | None, size: float) -> float:
    s = (raw or "normal").strip().lower()
    m = re.match(r"^([+-]?(?:\d+\.?\d*|\.\d+))\s*([a-z%]*)$", s)
    if not m:
        return 1.2
    n, unit = float(m.group(1)), m.group(2)
    if unit == "px":
        return round(n / size, 4)
    if unit == "%":
        return round(n / 100.0, 4)
    if unit in ("em", "rem", ""):
        return round(n, 4)
    return 1.2


def _letter_spacing(raw: str | None, size: float) -> float:
    s = (raw or "normal").strip().lower()
    m = re.match(r"^([+-]?(?:\d+\.?\d*|\.\d+))\s*([a-z%]*)$", s)
    if not m:
        return 0.0
    n, unit = float(m.group(1)), m.group(2)
    if unit == "px":
        return round(n / size, 4)
    if unit in ("em", "rem"):
        return round(n, 4)
    return 0.0


def _weight(raw: str | None) -> int:
    s = (raw or "400").strip().lower()
    if s == "bold":
        return 700
    if s == "normal":
        return 400
    n = _num(s)
    return int(round(n)) if n is not None else 400


def _mode(weighted: dict, default=None):
    """Ağırlığı en yüksek anahtar; eşitlikte anahtar sıralaması."""
    if not weighted:
        return default
    return sorted(weighted.items(), key=lambda kv: (-kv[1], str(kv[0])))[0][0]


def _type_style(els: list[ElementRecord]) -> TypeStyle | None:
    fam: dict[str, float] = defaultdict(float)
    size: dict[float, float] = defaultdict(float)
    wt: dict[int, float] = defaultdict(float)
    lh: dict[float, float] = defaultdict(float)
    ls: dict[float, float] = defaultdict(float)
    n = 0
    for e in els:
        s = _size(e)
        if s is None:
            continue
        w = max(float(e.area), 1e-9)
        n += 1
        fam[primary_family(e.styles.get("font-family", ""))] += w
        size[round(s, 4)] += w
        wt[_weight(e.styles.get("font-weight"))] += w
        lh[_line_height(e.styles.get("line-height"), s)] += w
        ls[_letter_spacing(e.styles.get("letter-spacing"), s)] += w
    if n == 0:
        return None
    return TypeStyle(
        font_family=_mode(fam, ""),
        font_size_px=_mode(size),
        line_height=_mode(lh),
        letter_spacing_em=_mode(ls),
        font_weight=_mode(wt),
        samples=n,
    )


def _family_stack(els: list[ElementRecord]) -> tuple[str, str] | None:
    """Alan ağırlıklı en sık (ana aile, ham zincir)."""
    fam: dict[str, float] = defaultdict(float)
    stacks: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for e in els:
        stack = (e.styles.get("font-family") or "").strip()
        if not stack:
            continue
        f = primary_family(stack)
        w = max(float(e.area), 1e-9)
        fam[f] += w
        stacks[f][stack] += w
    if not fam:
        return None
    top = _mode(fam)
    return top, _mode(stacks[top])


def _snap_ratio(measured: float) -> float:
    return sorted(TYPE_SCALE_RATIOS, key=lambda r: (abs(r - measured), r))[0]


def mine_typography(snapshot: RawSnapshot) -> Typography:
    els = snapshot.elements
    by_tag: dict[str, list[ElementRecord]] = defaultdict(list)
    for e in els:
        by_tag[e.tag].append(e)

    styles: dict[str, TypeStyle] = {}
    for tag in _STYLE_TAGS:
        group = by_tag.get(tag, [])
        with_text = [e for e in group if e.text_length > 0]
        ts = _type_style(with_text or group)
        if ts is not None:
            styles[tag] = ts

    text_els = [e for e in els if e.text_length > 0]

    body_pool = [e for e in text_els if e.tag in _BODY_TAGS] or text_els
    body = _family_stack(body_pool)
    if body is None:
        root = next((e for e in els if e.tag in ("body", "html")), None)
        body = _family_stack([root]) if root is not None else None
    body_family, body_stack = body if body else ("sans-serif", "sans-serif")

    display = _family_stack([e for e in text_els if e.tag in _DISPLAY_TAGS]) or (body_family, body_stack)

    mono_pool = [e for e in els if e.tag in _MONO_TAGS]
    mono_pool = [e for e in mono_pool if e.text_length > 0] or mono_pool
    mono_pool = [e for e in mono_pool if is_monospace(e.styles.get("font-family", ""))]
    mono = _family_stack(mono_pool)

    usage: dict[str, float] = defaultdict(float)
    usage_stacks: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for e in text_els:
        stack = (e.styles.get("font-family") or "").strip()
        if not stack:
            continue
        f = primary_family(stack)
        w = max(float(e.area), 1e-9)
        usage[f] += w
        usage_stacks[f][stack] += w
    total = sum(usage.values())
    families = [
        FontUsage(
            family=f,
            stack=_mode(usage_stacks[f]),
            weight=(w / total if total > 0 else 0.0),
            is_monospace=is_monospace(_mode(usage_stacks[f])),
        )
        for f, w in sorted(usage.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    base = styles["p"].font_size_px if "p" in styles else 16.0
    ratios: list[float] = []
    for level in range(1, 7):
        st = styles.get(f"h{level}")
        if st is None or st.font_size_px <= base:
            continue
        steps = max(1, 5 - level)
        ratios.append((st.font_size_px / base) ** (1.0 / steps))
    measured = round(statistics.median(ratios), 4) if ratios else 1.25

    return Typography(
        body_family=body_family,
        body_stack=body_stack,
        display_family=display[0],
        display_stack=display[1],
        mono_family=mono[0] if mono else None,
        mono_stack=mono[1] if mono else None,
        families=families,
        styles=styles,
        base_size_px=base,
        measured_ratio=measured,
        scale_ratio=_snap_ratio(measured),
        font_faces=[f.model_copy(deep=True) for f in snapshot.font_faces],
        font_links=list(snapshot.font_links),
    )
