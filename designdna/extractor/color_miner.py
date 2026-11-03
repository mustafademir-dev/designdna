"""Renk madenciliği: RawSnapshot -> ColorAnalysis (saf Python, tarayıcısız).

Kurallar için CONTRACTS.md §3.5. Tüm sıralamalar ikincil anahtarla (hex/isim)
çözüldüğü için çıktı %100 deterministiktir.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable

from designdna.models import (
    ColorAnalysis,
    ColorCluster,
    ColorRoles,
    ColorToken,
    ElementRecord,
    GradientToken,
    RawSnapshot,
    TokenVar,
)
from designdna.utils.color_math import (
    RGB,
    composite,
    contrast_ratio,
    delta_e_ok,
    hex_to_rgb,
    oklch_to_rgb,
    parse_color,
    rgb_to_hex,
    rgb_to_oklch,
)

CLUSTER_DELTA_E = 0.03

_SURFACE_RELAXED_DELTA_E = 0.01
_ACCENT_MIN_CHROMA = 0.05
_MUTED_MAX_CHROMA = 0.06
_MUTED_MIN_DELTA_E = 0.05
_WHITE: RGB = (1.0, 1.0, 1.0)

_BUTTON_INPUT_TYPES = ("button", "submit", "reset")
_CARD_EXCLUDED_TAGS = ("html", "body", "header", "nav", "footer")
_FORM_TAGS = ("input", "textarea", "select", "button")
_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_BADGE_WORDS = ("badge", "chip", "pill", "tag", "active", "selected", "current")
_SIDES = ("top", "right", "bottom", "left")

_ROLE_ORDER = ("background", "surface", "text-primary", "text-muted", "accent", "border")


# ---------------------------------------------------------------------------
# Kümeleme
# ---------------------------------------------------------------------------


def _cluster_members(samples: list[tuple[str, float]]) -> list[tuple[str, float, list[int]]]:
    """(merkez_hex, toplam_ağırlık, örnek_indeksleri) listesi; ağırlık azalan, hex artan."""
    agg: dict[str, float] = defaultdict(float)
    idxs: dict[str, list[int]] = defaultdict(list)
    for i, (hx, w) in enumerate(samples):
        key = hx.lower()
        agg[key] += float(w)
        idxs[key].append(i)
    order = sorted(agg, key=lambda h: (-agg[h], h))
    centers: list[tuple[str, RGB]] = []
    weights: list[float] = []
    members: list[list[int]] = []
    for hx in order:
        rgb = hex_to_rgb(hx)
        best = -1
        best_d = CLUSTER_DELTA_E
        for ci, (_, crgb) in enumerate(centers):
            d = delta_e_ok(rgb, crgb)
            if d < best_d:
                best, best_d = ci, d
        if best < 0:
            centers.append((hx, rgb))
            weights.append(agg[hx])
            members.append(list(idxs[hx]))
        else:
            weights[best] += agg[hx]
            members[best].extend(idxs[hx])
    out = [(centers[i][0], weights[i], sorted(members[i])) for i in range(len(centers))]
    out.sort(key=lambda t: (-t[1], t[0]))
    return out


def _round_lch(lch: tuple[float, float, float]) -> tuple[float, float, float]:
    return (round(lch[0], 4), round(lch[1], 4), round(lch[2], 2))


def cluster_colors(samples: list[tuple[str, float]]) -> list[ColorCluster]:
    """Ağırlığa göre azalan (eşitlikte hex artan) açgözlü OKLab kümeleme."""
    groups = _cluster_members(samples)
    total = sum(g[1] for g in groups)
    clusters: list[ColorCluster] = []
    for hx, w, mem in groups:
        share = w / total if total > 0 else 1.0 / len(groups)
        clusters.append(
            ColorCluster(
                hex=hx,
                oklch=_round_lch(rgb_to_oklch(hex_to_rgb(hx))),
                weight=share,
                count=len(mem),
                roles=[],
            )
        )
    return clusters


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _rgba(styles: dict[str, str], key: str) -> tuple[float, float, float, float]:
    parsed = parse_color(styles.get(key, "") or "")
    if parsed is None:
        return (0.0, 0.0, 0.0, 0.0)
    return parsed


def _px(value: str | None) -> float:
    if not value:
        return 0.0
    m = re.match(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+))", value)
    return float(m.group(1)) if m else 0.0


def _effective_map(snapshot: RawSnapshot) -> dict[int, RGB]:
    by_idx = {e.idx: e for e in snapshot.elements}
    memo: dict[int, RGB] = {}

    def resolve(idx: int) -> None:
        chain: list[int] = []
        cur: int | None = idx
        seen: set[int] = set()
        while cur is not None and cur in by_idx and cur not in memo and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            cur = by_idx[cur].parent_idx
        base = memo[cur] if cur is not None and cur in memo else _WHITE
        for i in reversed(chain):
            rgba = _rgba(by_idx[i].styles, "background-color")
            base = composite(rgba, base) if rgba[3] > 0 else base
            memo[i] = base

    for e in snapshot.elements:
        resolve(e.idx)
    return memo


def effective_background(snapshot: RawSnapshot, idx: int) -> RGB:
    """Eleman ve atalarının background-color'larını alttan üste composite eder (en altta beyaz)."""
    return _effective_map(snapshot).get(idx, _WHITE)


def _is_button(el: ElementRecord) -> bool:
    if el.tag == "button" or el.role == "button":
        return True
    if el.tag == "input" and (el.input_type or "") in _BUTTON_INPUT_TYPES:
        return True
    return el.tag == "a" and any("btn" in c.lower() or "button" in c.lower() for c in el.classes)


def _is_input(el: ElementRecord) -> bool:
    if el.tag in ("textarea", "select"):
        return True
    return el.tag == "input" and (el.input_type or "") not in _BUTTON_INPUT_TYPES


def _border_sides(styles: dict[str, str]) -> list[str]:
    """Görünür kenarlıklı kenarların renk anahtarları."""
    out = []
    for side in _SIDES:
        width = _px(styles.get(f"border-{side}-width"))
        style = (styles.get(f"border-{side}-style") or "none").strip().lower()
        if width >= 1 and style not in ("none", "hidden"):
            out.append(f"border-{side}-color")
    return out


def _has_shadow(styles: dict[str, str]) -> bool:
    return (styles.get("box-shadow") or "none").strip().lower() not in ("", "none")


def _card_idxs(snapshot: RawSnapshot, eff: dict[int, RGB]) -> set[int]:
    """§3.6 kart kuralı (component_miner'dan bağımsız özel kopya)."""
    by_idx = {e.idx: e for e in snapshot.elements}
    has_text_desc: set[int] = set()
    for e in snapshot.elements:
        if e.tag in _HEADING_TAGS or e.text_length > 0:
            cur = e.parent_idx
            seen: set[int] = set()
            while cur is not None and cur in by_idx and cur not in seen:
                seen.add(cur)
                has_text_desc.add(cur)
                cur = by_idx[cur].parent_idx
    cards: set[int] = set()
    for e in snapshot.elements:
        if e.tag in _CARD_EXCLUDED_TAGS or e.tag in _FORM_TAGS or _is_button(e) or _is_input(e):
            continue
        if e.area < 4000 or e.idx not in has_text_desc:
            continue
        parent_bg = eff.get(e.parent_idx, _WHITE) if e.parent_idx is not None else _WHITE
        own = _rgba(e.styles, "background-color")
        visible_bg = own[3] > 0 and delta_e_ok(eff[e.idx], parent_bg) >= 0.02
        if visible_bg or _border_sides(e.styles) or _has_shadow(e.styles):
            cards.add(e.idx)
    return cards


def _is_badge(el: ElementRecord) -> bool:
    for c in el.classes:
        for part in re.split(r"[^a-z0-9]+", c.lower()):
            if part in _BADGE_WORDS:
                return True
    return False


def _mk_token(hx: str, weight: float, raw: str | None = None) -> ColorToken:
    return ColorToken(hex=hx, oklch=_round_lch(rgb_to_oklch(hex_to_rgb(hx))), weight=weight, raw=raw)


def _shift_l(hx: str, delta: float) -> str:
    L, c, h = rgb_to_oklch(hex_to_rgb(hx))
    return rgb_to_hex(oklch_to_rgb((min(1.0, max(0.0, L + delta)), c, h)))


def _lightness(hx: str) -> float:
    return rgb_to_oklch(hex_to_rgb(hx))[0]


def _chroma(hx: str) -> float:
    return rgb_to_oklch(hex_to_rgb(hx))[1]


def _de(a: str, b: str) -> float:
    return delta_e_ok(hex_to_rgb(a), hex_to_rgb(b))


_Sample = tuple[str, float, "str | None"]  # hex, weight, raw


def _raw_map(samples: list[_Sample]) -> dict[str, str]:
    """hex -> o hex'e en çok ağırlık veren ham ifade."""
    best: dict[str, tuple[float, str]] = {}
    for hx, w, raw in samples:
        if raw is None:
            continue
        cur = best.get(hx)
        if cur is None or w > cur[0] or (w == cur[0] and raw < cur[1]):
            best[hx] = (w, raw)
    return {h: v[1] for h, v in best.items()}


def _cluster_samples(samples: list[_Sample]) -> list[ColorCluster]:
    return cluster_colors([(h, w) for h, w, _ in samples])


def _token_role(name: str) -> str | None:
    n = name.lower().lstrip("-")
    parts = [p for p in re.split(r"[^a-z0-9]+", n) if p]
    is_fg = "foreground" in n or "text" in parts or "fg" in parts or "ink" in parts
    if "border" in n or "outline" in parts:
        return "border"
    if "muted" in n or "subtle" in parts:
        return "text-muted" if is_fg else None
    if is_fg:
        blocked = ("primary", "accent", "card", "popover", "secondary", "destructive", "brand", "surface", "panel")
        return None if any(w in n for w in blocked) else "text-primary"
    if "accent" in n or "primary" in n or "brand" in n:
        return "accent"
    if "surface" in n or "card" in n or "panel" in n:
        return "surface"
    if "background" in n or "bg" in parts:
        return "background"
    return None


def _token_colors(
    tokens: list[TokenVar] | None, mode: str, bg: RGB
) -> dict[str, list[tuple[str, str]]]:
    """rol -> [(hex, ham değer)] (token sırasıyla); yalnızca snapshot'ın doğal temasına uyan renk token'ları."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    other = "light" if mode == "dark" else "dark"
    for t in tokens or []:
        if t.kind != "color" or t.media or other in t.selector.lower():
            continue
        role = _token_role(t.name)
        rgba = parse_color(t.value)
        if role is None or rgba is None:
            continue
        hx = rgb_to_hex(composite(rgba, bg)) if rgba[3] < 1 else rgb_to_hex((rgba[0], rgba[1], rgba[2]))
        out[role].append((hx, t.value))
    return out


def _token_match(
    cands: list[tuple[str, str]],
    clusters: list[ColorCluster],
    accept: Callable[[str], bool] | None = None,
) -> tuple[str, str, float] | None:
    """İlk eşleşen token -> (hex, ham, en yakın kümenin ağırlığı)."""
    for hx, raw in cands:
        if accept is not None and not accept(hx):
            continue
        near = [c for c in clusters if _de(hx, c.hex) < CLUSTER_DELTA_E]
        if near:
            near.sort(key=lambda c: (_de(hx, c.hex), c.hex))
            return hx, raw, near[0].weight
    return None


# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------


def mine_colors(snapshot: RawSnapshot, tokens: list[TokenVar] | None = None) -> ColorAnalysis:
    bg_rgb = hex_to_rgb(snapshot.dominant_background)
    bg_hex = rgb_to_hex(bg_rgb)
    eff = _effective_map(snapshot)
    cards = _card_idxs(snapshot, eff)
    tok = _token_colors(tokens, snapshot.natural_mode, bg_rgb)
    dark = _lightness(bg_hex) < 0.5
    root_area = max((e.area for e in snapshot.elements), default=1.0)

    palette_samples: list[tuple[str, float, str | None, tuple[str, ...]]] = [
        (bg_hex, root_area, None, ("background",))
    ]
    text_samples: list[_Sample] = []
    border_samples: list[_Sample] = []
    surface_samples: list[_Sample] = []
    accent_samples: list[_Sample] = []
    button_bgs: list[_Sample] = []
    bg_samples: list[tuple[str, float]] = [(bg_hex, root_area)]

    for e in snapshot.elements:
        st = e.styles
        area = float(e.area)
        own = _rgba(st, "background-color")
        eff_hex = rgb_to_hex(eff[e.idx])
        own_raw = st.get("background-color") if own[3] > 0 else None
        is_btn = _is_button(e)
        badge = _is_badge(e)

        if own[3] > 0 and e.tag not in ("html", "body"):
            tags = ["background"]
            bg_samples.append((eff_hex, area))
            if e.idx in cards:
                tags.append("surface")
                surface_samples.append((eff_hex, area, own_raw))
            if is_btn or badge:
                tags.append("accent")
                accent_samples.append((eff_hex, area, own_raw))
                if is_btn:
                    button_bgs.append((eff_hex, area, own_raw))
            palette_samples.append((eff_hex, area, own_raw, tuple(tags)))

        if e.text_length > 0:
            c = _rgba(st, "color")
            if c[3] > 0:
                hx = rgb_to_hex(composite(c, eff[e.idx]))
                raw = st.get("color")
                tags = ["text-primary", "text-muted"]
                text_samples.append((hx, area, raw))
                if (e.href and e.tag == "a") or badge:
                    tags.append("accent")
                    accent_samples.append((hx, area, raw))
                palette_samples.append((hx, area, raw, tuple(tags)))

        for key in _border_sides(st):
            c = _rgba(st, key)
            if c[3] <= 0:
                continue
            hx = rgb_to_hex(composite(c, eff[e.idx]))
            border_samples.append((hx, area / 4.0, st.get(key)))
            palette_samples.append((hx, area / 4.0, st.get(key), ("border",)))

    # ---- background (her zaman dominant_background)
    bg_clusters = cluster_colors(bg_samples)
    bg_share = next((c.weight for c in bg_clusters if _de(bg_hex, c.hex) < CLUSTER_DELTA_E), 1.0)
    background = _mk_token(bg_hex, bg_share, None)

    # ---- surface
    surf_pool = [c for c in _cluster_samples(surface_samples) if _de(c.hex, bg_hex) >= CLUSTER_DELTA_E]
    if not surf_pool:
        relaxed = [s for s in surface_samples if _de(s[0], bg_hex) >= _SURFACE_RELAXED_DELTA_E]
        surf_pool = _cluster_samples(relaxed)
    surf_raw = _raw_map(surface_samples)
    tmatch = _token_match(
        tok.get("surface", []), surf_pool, accept=lambda h: _de(h, bg_hex) >= CLUSTER_DELTA_E
    )
    if tmatch is not None:
        surface = _mk_token(tmatch[0], tmatch[2], tmatch[1])
    elif surf_pool:
        surface = _mk_token(surf_pool[0].hex, surf_pool[0].weight, surf_raw.get(surf_pool[0].hex))
    else:
        surface = _mk_token(_shift_l(bg_hex, 0.03 if dark else -0.03), 0.0, None)

    # ---- text-primary
    text_clusters = _cluster_samples(text_samples)
    text_raw = _raw_map(text_samples)

    def _contrast(hx: str) -> float:
        return contrast_ratio(hex_to_rgb(hx), bg_rgb)

    primary_pool = [c for c in text_clusters if _contrast(c.hex) >= 3.0] or text_clusters
    tmatch = _token_match(tok.get("text-primary", []), primary_pool)
    if tmatch is not None:
        text_primary = _mk_token(tmatch[0], tmatch[2], tmatch[1])
    elif primary_pool:
        c0 = primary_pool[0]
        text_primary = _mk_token(c0.hex, c0.weight, text_raw.get(c0.hex))
    else:
        text_primary = _mk_token("#ffffff" if dark else "#000000", 0.0, None)

    # ---- text-muted
    p_hex = text_primary.hex
    p_contrast = _contrast(p_hex)

    def _muted_ok(hx: str) -> bool:
        return (
            _de(hx, p_hex) >= _MUTED_MIN_DELTA_E
            and 2.0 <= _contrast(hx) < p_contrast
            and _chroma(hx) <= _MUTED_MAX_CHROMA
        )

    muted_pool = [c for c in text_clusters if _muted_ok(c.hex)]
    tmatch = _token_match(tok.get("text-muted", []), text_clusters, accept=_muted_ok)
    if tmatch is not None:
        text_muted = _mk_token(tmatch[0], tmatch[2], tmatch[1])
    elif muted_pool:
        c0 = muted_pool[0]
        text_muted = _mk_token(c0.hex, c0.weight, text_raw.get(c0.hex))
    else:
        direction = 1.0 if _lightness(bg_hex) > _lightness(p_hex) else -1.0
        text_muted = _mk_token(_shift_l(p_hex, 0.25 * direction), 0.0, None)

    # ---- accent
    acc_clusters = _cluster_samples(accent_samples)
    acc_raw = _raw_map(accent_samples)
    chromatic = [c for c in acc_clusters if c.oklch[1] >= _ACCENT_MIN_CHROMA]
    tmatch = _token_match(tok.get("accent", []), acc_clusters)
    if tmatch is not None:
        accent = _mk_token(tmatch[0], tmatch[2], tmatch[1])
    elif chromatic:
        c0 = chromatic[0]
        accent = _mk_token(c0.hex, c0.weight, acc_raw.get(c0.hex))
    elif button_bgs:
        total_btn = sum(s[1] for s in button_bgs) or 1.0
        best = sorted(button_bgs, key=lambda s: (-round(_chroma(s[0]), 4), -s[1], s[0]))[0]
        accent = _mk_token(best[0], best[1] / total_btn, best[2])
    else:
        accent = _mk_token(text_primary.hex, 0.0, text_primary.raw)

    # ---- border
    border_clusters = _cluster_samples(border_samples)
    border_raw = _raw_map(border_samples)
    tmatch = _token_match(tok.get("border", []), border_clusters)
    if tmatch is not None:
        border = _mk_token(tmatch[0], tmatch[2], tmatch[1])
    elif border_clusters:
        c0 = border_clusters[0]
        border = _mk_token(c0.hex, c0.weight, border_raw.get(c0.hex))
    else:
        border = _mk_token(_shift_l(bg_hex, 0.1 if dark else -0.1), 0.0, None)

    roles = ColorRoles(
        background=background,
        surface=surface,
        text_primary=text_primary,
        text_muted=text_muted,
        accent=accent,
        border=border,
    )

    # ---- palette
    groups = _cluster_members([(h, w) for h, w, _, _ in palette_samples])
    total = sum(g[1] for g in groups)
    chosen = {
        "background": roles.background.hex,
        "surface": roles.surface.hex,
        "text-primary": roles.text_primary.hex,
        "text-muted": roles.text_muted.hex,
        "accent": roles.accent.hex,
        "border": roles.border.hex,
    }
    palette: list[ColorCluster] = []
    for hx, w, mem in groups:
        tag_set: set[str] = set()
        for i in mem:
            tag_set.update(palette_samples[i][3])
        for role, rhex in chosen.items():
            if _de(hx, rhex) < CLUSTER_DELTA_E:
                tag_set.add(role)
        palette.append(
            ColorCluster(
                hex=hx,
                oklch=_round_lch(rgb_to_oklch(hex_to_rgb(hx))),
                weight=w / total if total > 0 else 1.0 / len(groups),
                count=len(mem),
                roles=[r for r in _ROLE_ORDER if r in tag_set],
            )
        )

    return ColorAnalysis(roles=roles, palette=palette, gradients=_gradient_tokens(snapshot))


def _gradient_tokens(snapshot: RawSnapshot) -> list[GradientToken]:
    agg: dict[tuple[str, str], float] = defaultdict(float)
    for g in snapshot.gradients:
        agg[(g.kind, g.value)] += float(g.area)
    if not agg:
        return []
    total = sum(agg.values())
    items = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0][1], kv[0][0]))
    return [
        GradientToken(
            kind=kind,  # type: ignore[arg-type]
            value=value,
            weight=(area / total if total > 0 else 1.0 / len(items)),
        )
        for (kind, value), area in items
    ]
