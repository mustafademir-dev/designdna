"""W3C Design Tokens (DTCG) çıktısı."""

from __future__ import annotations

import json
from typing import Any

from designdna.models import DesignSystem

from ._common import (
    COLOR_ROLES, family_list, kebab, num, parse_box_shadow, parse_easing, px,
    sorted_sizes, sorted_spacing,
)


def _t(value: Any, type_: str) -> dict[str, Any]:
    return {"$value": value, "$type": type_}


def build_tokens(ds: DesignSystem) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for theme in ("light", "dark"):
        colors = getattr(ds, theme)
        tree.setdefault("color", {})[theme] = {
            kebab(r): _t(getattr(colors, r), "color") for r in COLOR_ROLES
        }
    ty = ds.typography
    tree["font"] = {
        "family": {
            "sans": _t(family_list(ty.sans.stack), "fontFamily"),
            "mono": _t(family_list(ty.mono.stack), "fontFamily"),
            "display": _t(family_list(ty.display.stack), "fontFamily"),
        },
        "size": {k: _t(px(v), "dimension") for k, v in sorted_sizes(ds)},
        "weight": {k: _t(int(v), "fontWeight") for k, v in sorted(ty.weights.items(), key=lambda kv: (kv[1], kv[0]))},
        "lineHeight": {k: _t(float(v), "number") for k, v in sorted(ty.line_heights.items(), key=lambda kv: (kv[1], kv[0]))},
        "letterSpacing": {k: _t(f"{num(v)}em", "dimension") for k, v in sorted(ty.letter_spacing.items(), key=lambda kv: (kv[1], kv[0]))},
    }
    tree["spacing"] = {k: _t(px(v), "dimension") for k, v in sorted_spacing(ds)}
    tree["radius"] = {k: _t(px(v), "dimension") for k, v in sorted(ds.radius.items(), key=lambda kv: (kv[1], kv[0]))}
    shadows: dict[str, Any] = {}
    for k in ("sm", "md", "lg"):
        layers = parse_box_shadow(getattr(ds.shadows, k))
        if layers:
            shadows[k] = _t(layers if len(layers) > 1 else layers[0], "shadow")
    tree["shadow"] = shadows
    tree["duration"] = {"base": _t(f"{num(ds.motion.duration_ms)}ms", "duration")}
    tree["easing"] = {"base": _t(parse_easing(ds.motion.easing), "cubicBezier")}
    return tree


def render_tokens_json(ds: DesignSystem) -> str:
    return json.dumps(build_tokens(ds), indent=2, ensure_ascii=False) + "\n"
