"""CSS custom property (token) madenciliği — saf Python, tarayıcı yok."""

from __future__ import annotations

import re

from designdna.models import CustomProperty, RawSnapshot, TokenKind, TokenVar
from designdna.utils.color_math import parse_color

NOISE_PREFIXES = (
    "--tw-",
    "--wp-",
    "--wp--",
    "--bs-",
    "--chakra-",
    "--mantine-",
    "--rs-",
    "--swiper-",
    "--fa-",
    "--toastify-",
)

_DIM_RE = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)(?:px|rem|em)$", re.IGNORECASE)
_DIM_LIST_RE = re.compile(r"^(?:-?(?:\d+\.?\d*|\.\d+)(?:px|rem|em)?\s*)+$", re.IGNORECASE)
_SHADOW_RE = re.compile(
    r"^(?:inset\s+)?-?(?:\d+\.?\d*|\.\d+)(?:px|rem|em)?\s+-?(?:\d+\.?\d*|\.\d+)(?:px|rem|em)?\s+\S",
    re.IGNORECASE,
)
_GENERIC_FONTS = (
    "sans-serif",
    "serif",
    "monospace",
    "system-ui",
    "ui-sans-serif",
    "ui-serif",
    "ui-monospace",
    "cursive",
    "fantasy",
)
_FONT_NAME_EXCLUDE = ("weight", "style", "size", "variation", "feature", "stretch", "height", "spacing")
_VAR_START = re.compile(r"var\(\s*(--[A-Za-z0-9_\-]+)\s*")
_MAX_DEPTH = 5


def is_noise(name: str) -> bool:
    """Framework gürültüsü (--tw-*, --wp-*, --bs-* ...) mü."""
    return name.strip().lower().startswith(NOISE_PREFIXES)


def classify_token(name: str, value: str) -> TokenKind | None:
    """Çözülmüş (literal) değerin türünü döndürür; çözülemezse None."""
    v = value.strip()
    n = name.strip().lower()
    if not v or "var(" in v.lower():
        return None
    is_color = parse_color(v) is not None
    if "shadow" in n:
        if is_color:
            return "color"
        if _DIM_RE.match(v):
            return "dimension"
        return "shadow"
    if ("radius" in n or "rounded" in n) and _DIM_LIST_RE.match(v) and re.search(r"\d", v):
        return "radius"
    if is_color:
        return "color"
    if _DIM_RE.match(v):
        return "dimension"
    if _SHADOW_RE.match(v) and re.search(r"(rgb|hsl|oklch|#|transparent|black|white)", v, re.IGNORECASE):
        return "shadow"
    lv = v.lower()
    if any(g in lv for g in _GENERIC_FONTS):
        return "font"
    if ("font" in n or "family" in n) and not any(x in n for x in _FONT_NAME_EXCLUDE):
        if re.search(r"[A-Za-z]", v) and not re.fullmatch(r"-?[\d.]+", v):
            return "font"
    return None


def _selector_rank(selector: str) -> int | None:
    best: int | None = None
    for part in selector.split(","):
        p = part.strip()
        rank: int | None = None
        if p == ":root":
            rank = 0
        elif p == "html":
            rank = 1
        elif p == "body":
            rank = 2
        elif "[data-theme" in p:
            rank = 3
        if rank is not None and (best is None or rank < best):
            best = rank
    return best


def _substitute_once(value: str, lookup) -> str | None:
    """Değerdeki en dıştaki tüm var(...) referanslarını bir seviye çözer."""
    out: list[str] = []
    pos = 0
    while True:
        m = _VAR_START.search(value, pos)
        if not m:
            out.append(value[pos:])
            return "".join(out)
        out.append(value[pos : m.start()])
        i = m.end()
        depth = 1
        fallback: str | None = None
        start_fb: int | None = None
        while i < len(value) and depth > 0:
            ch = value[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            elif ch == "," and depth == 1 and start_fb is None:
                start_fb = i + 1
            i += 1
        if depth != 0:
            return None
        if start_fb is not None:
            fallback = value[start_fb:i].strip()
        resolved = lookup(m.group(1))
        if resolved is None:
            resolved = fallback
        if resolved is None:
            return None
        out.append(resolved)
        pos = i + 1


def mine_tokens(snapshot: RawSnapshot) -> list[TokenVar]:
    props: list[CustomProperty] = snapshot.custom_properties
    # arama tablosu: (selector, media) -> {ad: değer}; sonraki tanım öncekini ezer
    scoped: dict[tuple[str, str | None], dict[str, str]] = {}
    ranked: dict[str, tuple[tuple[int, int], str]] = {}
    for order, p in enumerate(props):
        scoped.setdefault((p.selector, p.media), {})[p.name] = p.value.strip()
        rank = _selector_rank(p.selector)
        key = (rank if rank is not None else 9, 0 if p.media is None else 1)
        cur = ranked.get(p.name)
        if cur is None or key <= cur[0]:
            ranked[p.name] = (key, p.value.strip())

    results: list[tuple[tuple[int, str, str, str], TokenVar]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for p in props:
        rank = _selector_rank(p.selector)
        if rank is None or is_noise(p.name):
            continue
        ident = (p.name, p.selector, p.media)
        if ident in seen:
            continue
        seen.add(ident)
        table = scoped[(p.selector, p.media)]

        def lookup(name: str, table=table) -> str | None:
            if is_noise(name):
                return None
            if name in table:
                return table[name]
            hit = ranked.get(name)
            return hit[1] if hit else None

        value = table[p.name]
        ok = True
        for _ in range(_MAX_DEPTH):
            if "var(" not in value.lower():
                break
            nxt = _substitute_once(value, lookup)
            if nxt is None:
                ok = False
                break
            value = nxt.strip()
        if not ok or "var(" in value.lower():
            continue
        kind = classify_token(p.name, value)
        if kind is None:
            continue
        results.append(
            (
                (rank, p.name, p.selector, p.media or ""),
                TokenVar(name=p.name, value=value, kind=kind, selector=p.selector, media=p.media),
            )
        )
    results.sort(key=lambda t: t[0])
    return [t[1] for t in results]
