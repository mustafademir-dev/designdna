"""Ortak yardımcılar: Jinja ortamı, biçimlendirme, renk ve gölge ayrıştırma."""

from __future__ import annotations

import json
import re

from jinja2 import Environment, PackageLoader, select_autoescape

from designdna.models import DesignSystem
from designdna.utils.color_math import (
    contrast_ratio,
    hex_to_rgb,
    oklch_css,
    parse_color,
    rgb_to_hex,
)

_ENV: Environment | None = None


def get_env() -> Environment:
    global _ENV
    if _ENV is None:
        env = Environment(
            loader=PackageLoader("designdna.generators", "templates"),
            autoescape=select_autoescape(enabled_extensions=("html.j2",), default=False),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        env.filters["js"] = lambda v: json.dumps(v, ensure_ascii=False)
        _ENV = env
    return _ENV


def render(template: str, **ctx: object) -> str:
    return get_env().get_template(template).render(**ctx)


def num(x: float) -> str:
    """8.0 -> '8', 1.25 -> '1.25'."""
    s = f"{float(x):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def px(x: float) -> str:
    return f"{num(x)}px"


def kebab(name: str) -> str:
    return name.replace("_", "-")


def css_safe(value: str) -> str:
    """CSS değerinden <style> bloğunu bozabilecek karakterleri atar."""
    return re.sub(r"[<>{};\\]", "", value)


def ratio(a_hex: str, b_hex: str) -> float:
    return contrast_ratio(hex_to_rgb(a_hex), hex_to_rgb(b_hex))


def oklch_of(hex_value: str) -> str:
    return oklch_css(hex_to_rgb(hex_value))


def family_list(stack: str) -> list[str]:
    return [p.strip().strip("'\"") for p in _split_top(stack, ",") if p.strip()]


def _split_top(text: str, sep: str) -> list[str]:
    parts, depth, cur, quote = [], 0, [], ""
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def _split_ws(text: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in text.strip():
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                parts.append("".join(cur))
                cur = []
            continue
        cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def color_with_alpha(value: str) -> str:
    """CSS rengi -> '#rrggbb' ya da '#rrggbbaa'."""
    rgba = parse_color(value)
    if rgba is None:
        return "#000000"
    base = rgb_to_hex(rgba[:3])
    if rgba[3] >= 0.9995:
        return base
    return f"{base}{round(rgba[3] * 255):02x}"


_LEN = re.compile(r"^-?\d*\.?\d+(px)?$")


def parse_box_shadow(value: str) -> list[dict[str, object]]:
    """CSS box-shadow -> DTCG shadow nesne listesi ('none' -> [])."""
    layers: list[dict[str, object]] = []
    if not value or value.strip().lower() == "none":
        return layers
    for raw in _split_top(value, ","):
        toks = _split_ws(raw)
        lengths: list[str] = []
        color = "#000000"
        inset = False
        for t in toks:
            if t.lower() == "inset":
                inset = True
            elif _LEN.match(t):
                lengths.append(px(float(t.removesuffix("px"))))
            else:
                color = color_with_alpha(t)
        while len(lengths) < 4:
            lengths.append("0px")
        layer: dict[str, object] = {
            "color": color,
            "offsetX": lengths[0],
            "offsetY": lengths[1],
            "blur": lengths[2],
            "spread": lengths[3],
        }
        if inset:
            layer["inset"] = True
        layers.append(layer)
    return layers


EASING_KEYWORDS: dict[str, list[float]] = {
    "ease": [0.25, 0.1, 0.25, 1.0],
    "ease-in": [0.42, 0.0, 1.0, 1.0],
    "ease-out": [0.0, 0.0, 0.58, 1.0],
    "ease-in-out": [0.42, 0.0, 0.58, 1.0],
    "linear": [0.0, 0.0, 1.0, 1.0],
}


def parse_easing(value: str) -> list[float]:
    v = value.strip().lower()
    if v in EASING_KEYWORDS:
        return list(EASING_KEYWORDS[v])
    m = re.match(r"cubic-bezier\(([^)]*)\)", v)
    if m:
        try:
            nums = [float(p) for p in m.group(1).split(",")]
            if len(nums) == 4:
                return nums
        except ValueError:
            pass
    return list(EASING_KEYWORDS["ease"])


def sorted_sizes(ds: DesignSystem) -> list[tuple[str, float]]:
    return sorted(ds.typography.sizes.items(), key=lambda kv: (kv[1], kv[0]))


def sorted_spacing(ds: DesignSystem) -> list[tuple[str, float]]:
    return sorted(ds.spacing.items(), key=lambda kv: (float(kv[0]) if kv[0].isdigit() else 1e9, kv[0]))


COLOR_ROLES = (
    "background", "surface", "text_primary", "text_muted", "accent", "accent_foreground",
    "border", "secondary", "secondary_foreground", "destructive", "destructive_foreground", "ring",
)
