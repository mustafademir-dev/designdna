"""Deterministik, saf-stdlib renk matematiği (sRGB, Linear RGB, OKLab, OKLCH, WCAG)."""

from __future__ import annotations

import math
import re

RGB = tuple[float, float, float]
RGBA = tuple[float, float, float, float]

_NAMED: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "lime": (0, 255, 0),
    "blue": (0, 0, 255),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "silver": (192, 192, 192),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "pink": (255, 192, 203),
    "cyan": (0, 255, 255),
    "aqua": (0, 255, 255),
    "magenta": (255, 0, 255),
    "fuchsia": (255, 0, 255),
    "maroon": (128, 0, 0),
    "navy": (0, 0, 128),
    "teal": (0, 128, 128),
    "olive": (128, 128, 0),
    "brown": (165, 42, 42),
    "gold": (255, 215, 0),
    "indigo": (75, 0, 130),
    "violet": (238, 130, 238),
    "crimson": (220, 20, 60),
    "coral": (255, 127, 80),
    "tomato": (255, 99, 71),
    "salmon": (250, 128, 114),
    "beige": (245, 245, 220),
    "ivory": (255, 255, 240),
    "lightgray": (211, 211, 211),
    "lightgrey": (211, 211, 211),
    "darkgray": (169, 169, 169),
    "darkgrey": (169, 169, 169),
    "whitesmoke": (245, 245, 245),
    "rebeccapurple": (102, 51, 153),
}

_NUM = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_FUNC_RE = re.compile(r"^([a-z]+)\(\s*(.*?)\s*\)$", re.DOTALL)
_NUM_UNIT_RE = re.compile(rf"^({_NUM})(%|deg|grad|rad|turn)?$")


# ---------------------------------------------------------------- helpers


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


# ---------------------------------------------------------------- transfer


def srgb_to_linear(c: float) -> float:
    a = abs(c)
    v = a / 12.92 if a <= 0.04045 else ((a + 0.055) / 1.055) ** 2.4
    return math.copysign(v, c) if c != 0 else 0.0


def linear_to_srgb(c: float) -> float:
    a = abs(c)
    v = a * 12.92 if a <= 0.0031308 else 1.055 * (a ** (1 / 2.4)) - 0.055
    return math.copysign(v, c) if c != 0 else 0.0


# ---------------------------------------------------------------- OKLab


def rgb_to_oklab(rgb: RGB) -> tuple[float, float, float]:
    r, g, b = (srgb_to_linear(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = math.cbrt(l), math.cbrt(m), math.cbrt(s)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_rgb(lab: tuple[float, float, float]) -> RGB:
    L, a, b = lab
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bl = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return (linear_to_srgb(r), linear_to_srgb(g), linear_to_srgb(bl))


def oklab_to_oklch(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    L, a, b = lab
    c = math.hypot(a, b)
    if c < 1e-4:
        return (L, c, 0.0)
    h = math.degrees(math.atan2(b, a)) % 360.0
    return (L, c, h)


def oklch_to_oklab(lch: tuple[float, float, float]) -> tuple[float, float, float]:
    L, c, h = lch
    hr = math.radians(h)
    return (L, c * math.cos(hr), c * math.sin(hr))


def rgb_to_oklch(rgb: RGB) -> tuple[float, float, float]:
    return oklab_to_oklch(rgb_to_oklab(rgb))


# ---------------------------------------------------------------- gamut


def in_gamut(rgb: RGB, eps: float = 1e-6) -> bool:
    return all(-eps <= c <= 1.0 + eps for c in rgb)


def _clamp_rgb(rgb: RGB) -> RGB:
    return (_clamp01(rgb[0]), _clamp01(rgb[1]), _clamp01(rgb[2]))


def gamut_map_oklch(lch: tuple[float, float, float]) -> RGB:
    """L ve H sabit, C ikili aramayla düşürülür; sonuç [0,1] içine kırpılır."""
    L, c, h = lch
    c = max(c, 0.0)
    direct = oklab_to_rgb(oklch_to_oklab((L, c, h)))
    if in_gamut(direct):
        return _clamp_rgb(direct)
    lo, hi = 0.0, c
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if in_gamut(oklab_to_rgb(oklch_to_oklab((L, mid, h)))):
            lo = mid
        else:
            hi = mid
    return _clamp_rgb(oklab_to_rgb(oklch_to_oklab((L, lo, h))))


def oklch_to_rgb(lch: tuple[float, float, float]) -> RGB:
    return gamut_map_oklch(lch)


# ---------------------------------------------------------------- hex


def rgb_to_hex(rgb: RGB) -> str:
    r, g, b = (_round_half_up(_clamp01(c) * 255.0) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_rgb(hex_str: str) -> RGB:
    parsed = _parse_hex(hex_str.strip())
    if parsed is None:
        raise ValueError(f"Geçersiz hex renk: {hex_str!r}")
    return (parsed[0], parsed[1], parsed[2])


def _parse_hex(s: str) -> RGBA | None:
    if not s.startswith("#"):
        return None
    h = s[1:]
    if not re.fullmatch(r"[0-9a-fA-F]+", h):
        return None
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h)
    if len(h) == 6:
        h += "ff"
    if len(h) != 8:
        return None
    v = [int(h[i : i + 2], 16) / 255.0 for i in range(0, 8, 2)]
    return (v[0], v[1], v[2], v[3])


# ---------------------------------------------------------------- composite


def composite(fg: RGBA, bg: RGB) -> RGB:
    a = _clamp01(fg[3])
    return (
        fg[0] * a + bg[0] * (1 - a),
        fg[1] * a + bg[1] * (1 - a),
        fg[2] * a + bg[2] * (1 - a),
    )


def composite_over(colors: list[RGBA], base: RGB = (1.0, 1.0, 1.0)) -> RGB:
    out = base
    for c in colors:
        out = composite(c, out)
    return out


# ---------------------------------------------------------------- metrics


def relative_luminance(rgb: RGB) -> float:
    r, g, b = (srgb_to_linear(_clamp01(c)) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: RGB, b: RGB) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = (la, lb) if la >= lb else (lb, la)
    return (hi + 0.05) / (lo + 0.05)


def delta_e_ok(a: RGB, b: RGB) -> float:
    la, lb = rgb_to_oklab(a), rgb_to_oklab(b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(la, lb)))


def normalize_hex(value: str, background: RGB = (1.0, 1.0, 1.0)) -> str | None:
    parsed = parse_color(value)
    if parsed is None:
        return None
    if parsed[3] < 1.0:
        return rgb_to_hex(composite(parsed, background))
    return rgb_to_hex((parsed[0], parsed[1], parsed[2]))


def oklch_css(rgb: RGB) -> str:
    L, c, h = rgb_to_oklch(rgb)
    return f"oklch({L:.3f} {c:.3f} {h:.2f})"


def hsl_components(rgb: RGB) -> tuple[float, float, float]:
    r, g, b = (_clamp01(c) for c in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    d = mx - mn
    if d < 1e-12:
        return (0.0, 0.0, l * 100.0)
    s = d / (1 - abs(2 * l - 1)) if 0 < l < 1 else 0.0
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return ((h * 60.0) % 360.0, s * 100.0, l * 100.0)


# ---------------------------------------------------------------- parsing


def _split_args(body: str) -> tuple[list[str], str | None] | None:
    """Fonksiyon gövdesini (bileşenler, alfa|None) olarak ayırır."""
    alpha: str | None = None
    if "/" in body:
        main, _, alpha_part = body.partition("/")
        if "/" in alpha_part:
            return None
        alpha = alpha_part.strip()
        if not alpha:
            return None
        parts = [p for p in re.split(r"[\s,]+", main.strip()) if p]
    else:
        parts = [p for p in re.split(r"[\s,]+", body.strip()) if p]
        if len(parts) == 4:
            alpha = parts.pop()
    return parts, alpha


def _num(tok: str) -> tuple[float, str] | None:
    m = _NUM_UNIT_RE.match(tok.strip().lower())
    if not m:
        return None
    return float(m.group(1)), m.group(2) or ""


def _alpha(tok: str | None) -> float | None:
    if tok is None:
        return 1.0
    n = _num(tok)
    if n is None or n[1] not in ("", "%"):
        return None
    v = n[0] / 100.0 if n[1] == "%" else n[0]
    return _clamp01(v)


def _channel(tok: str, scale: float) -> float | None:
    """rgb kanalı: sayı (0..255) veya yüzde -> 0..1."""
    n = _num(tok)
    if n is None or n[1] not in ("", "%"):
        return None
    v = n[0] / 100.0 if n[1] == "%" else n[0] / scale
    return _clamp01(v)


def _hue(tok: str) -> float | None:
    n = _num(tok)
    if n is None or n[1] == "%":
        return None
    v, unit = n
    if unit == "grad":
        v = v * 0.9
    elif unit == "rad":
        v = math.degrees(v)
    elif unit == "turn":
        v = v * 360.0
    return v % 360.0


def _hsl_to_rgb(h: float, s: float, l: float) -> RGB:
    def f(n: float) -> float:
        k = (n + h / 30.0) % 12
        a = s * min(l, 1 - l)
        return l - a * max(-1.0, min(k - 3, 9 - k, 1.0))

    return (f(0), f(8), f(4))


def parse_color(value: str) -> RGBA | None:
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    if not s:
        return None
    if s.startswith("#"):
        return _parse_hex(s)
    if s == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    if s in _NAMED:
        r, g, b = _NAMED[s]
        return (r / 255.0, g / 255.0, b / 255.0, 1.0)
    m = _FUNC_RE.match(s)
    if not m:
        return None
    name, body = m.group(1), m.group(2)
    if name == "color":
        return _parse_color_fn(body)
    if name not in ("rgb", "rgba", "hsl", "hsla", "oklch"):
        return None
    split = _split_args(body)
    if split is None:
        return None
    parts, atok = split
    if len(parts) != 3:
        return None
    a = _alpha(atok)
    if a is None:
        return None
    if name in ("rgb", "rgba"):
        ch = [_channel(p, 255.0) for p in parts]
        if any(c is None for c in ch):
            return None
        return (ch[0], ch[1], ch[2], a)  # type: ignore[return-value]
    if name in ("hsl", "hsla"):
        h = _hue(parts[0])
        sn, ln = _num(parts[1]), _num(parts[2])
        if h is None or sn is None or ln is None:
            return None
        sat = _clamp01(sn[0] / 100.0)
        lig = _clamp01(ln[0] / 100.0)
        r, g, b = _hsl_to_rgb(h, sat, lig)
        return (_clamp01(r), _clamp01(g), _clamp01(b), a)
    # oklch
    ln, cn = _num(parts[0]), _num(parts[1])
    h = _hue(parts[2])
    if ln is None or cn is None or h is None:
        return None
    L = ln[0] / 100.0 if ln[1] == "%" else ln[0]
    C = cn[0] * 0.4 / 100.0 if cn[1] == "%" else cn[0]
    r, g, b = oklch_to_rgb((_clamp01(L), max(C, 0.0), h))
    return (r, g, b, a)


def _parse_color_fn(body: str) -> RGBA | None:
    split = _split_args(body)
    if split is None:
        return None
    parts, atok = split
    # _split_args 4 parçada alfa sayar; color() için ilk parça uzay adıdır.
    if atok is not None and "/" not in body:
        parts.append(atok)
        atok = None
    if len(parts) != 4 or parts[0] not in ("srgb", "srgb-linear"):
        return None
    a = _alpha(atok)
    if a is None:
        return None
    ch: list[float] = []
    for p in parts[1:]:
        n = _num(p)
        if n is None or n[1] not in ("", "%"):
            return None
        ch.append(_clamp01(n[0] / 100.0 if n[1] == "%" else n[0]))
    if parts[0] == "srgb-linear":
        ch = [_clamp01(linear_to_srgb(c)) for c in ch]
    return (ch[0], ch[1], ch[2], a)
