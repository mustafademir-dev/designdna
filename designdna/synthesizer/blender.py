"""Birden çok SiteExtraction'ı rol bazlı harmanlayıp tek bir DesignSystem üretir."""

from __future__ import annotations

import logging
import re

from designdna import __version__
from designdna.errors import DesignDNAError
from designdna.models import (
    STANDARD_RADII,
    BlendReport,
    ComponentSpec,
    ComponentStats,
    ComponentStyle,
    ComponentSystem,
    ContrastFix,
    DesignSystem,
    FontSpec,
    HoverStyle,
    LayoutSystem,
    MotionSystem,
    RoleAssignment,
    ShadowSystem,
    SiteExtraction,
    SourceRef,
    SourceWeight,
    ThemeColors,
    ThemeMode,
    TypographySystem,
)
from designdna.utils.color_math import (
    contrast_ratio,
    hex_to_rgb,
    oklch_to_rgb,
    rgb_to_hex,
    rgb_to_oklch,
)

logger = logging.getLogger(__name__)

ELIGIBILITY_THRESHOLD = 0.2
NEUTRAL_ACCENT_MAX_CHROMA = 0.03

ROLE_ORDER = (
    "background",
    "surface",
    "text-primary",
    "text-muted",
    "border",
    "font-body",
    "font-mono",
    "spacing",
    "layout",
    "accent",
    "radius-control",
    "hover-style",
    "shadow",
    "font-display",
    "radius-card",
)
GROUP1 = ("background", "surface", "text-primary", "text-muted", "border", "font-body", "font-mono", "spacing", "layout")
GROUP2 = ("accent", "radius-control", "hover-style")
GROUP3 = ("shadow", "font-display", "radius-card")

_SMALL_SPACING = (0.0, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0)
_LARGE_SPACING = (32.0, 40.0, 48.0, 64.0, 80.0, 96.0, 128.0)
_BREAKPOINT_KEYS = (("sm", 640.0), ("md", 768.0), ("lg", 1024.0), ("xl", 1280.0), ("2xl", 1536.0))
_DEFAULT_MONO_STACK = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
_GENERIC_FAMILIES = ("sans-serif", "serif", "monospace", "system-ui", "cursive", "fantasy", "ui-monospace")

_DESTRUCTIVE = {"light": "#dc2626", "dark": "#ef4444"}


# --------------------------------------------------------------------------- yardımcılar


def normalize_weights(weights: list[float | None]) -> list[float]:
    """Ağırlıkları toplam 1.0 olacak şekilde normalize eder; None varsa hepsi eşit."""
    n = len(weights)
    if n == 0:
        return []
    if any(w is None for w in weights):
        return [1.0 / n] * n
    vals = [float(w) for w in weights]  # type: ignore[arg-type]
    if any(v < 0 for v in vals) or sum(vals) <= 0:
        return [1.0 / n] * n
    total = sum(vals)
    return [v / total for v in vals]


def quantize_radius(px: float) -> float:
    if px > 40:
        return 9999.0
    candidates = [float(r) for r in STANDARD_RADII[:-1]]
    return min(candidates, key=lambda c: (abs(c - px), c))


def quantize_spacing(px: float) -> float:
    pool = _SMALL_SPACING if px <= 24 else _LARGE_SPACING
    return min(pool, key=lambda c: (abs(c - px), c))


def _to_lch(hex_color: str) -> tuple[float, float, float]:
    return rgb_to_oklch(hex_to_rgb(hex_color))


def _from_lch(lch: tuple[float, float, float]) -> str:
    return rgb_to_hex(oklch_to_rgb(lch))


def _min_ratio(color: str, against: list[str]) -> float:
    rgb = hex_to_rgb(color)
    return min(contrast_ratio(rgb, hex_to_rgb(a)) for a in against)


def ensure_contrast(color: str, against: list[str], target: float) -> tuple[str, float, bool]:
    """Rengin `against` renklerine kontrastını (en düşük oran) hedefe çıkarır.

    Yalnızca OKLCH L kanalı ±0.02 adımla (en fazla 40 adım) kaydırılır; H ve C korunur,
    her adımda gamut mapping uygulanır. Ulaşılamazsa beyaz/siyah fallback seçilir.
    Dönüş: (hex, ulaşılan oran, hedefe ulaşıldı mı).
    """
    color = color.lower()
    ratio0 = _min_ratio(color, against)
    if ratio0 >= target:
        return color, ratio0, True

    lightness, chroma, hue = _to_lch(color)
    mean_l = sum(_to_lch(a)[0] for a in against) / len(against)
    if lightness > mean_l + 1e-6:
        direction = 1.0
    elif lightness < mean_l - 1e-6:
        direction = -1.0
    else:
        direction = 1.0 if mean_l < 0.5 else -1.0

    for step in range(1, 41):
        new_l = min(1.0, max(0.0, lightness + direction * 0.02 * step))
        candidate = _from_lch((new_l, chroma, hue))
        ratio = _min_ratio(candidate, against)
        if ratio >= target:
            return candidate, ratio, True
        if new_l in (0.0, 1.0):
            break

    white, black = "#ffffff", "#000000"
    r_white, r_black = _min_ratio(white, against), _min_ratio(black, against)
    ok = [(c, r) for c, r in ((white, r_white), (black, r_black)) if r >= target]
    if ok:
        preferred = white if direction > 0 else black
        for c, r in ok:
            if c == preferred:
                return c, r, True
        return ok[0][0], ok[0][1], True
    best, best_ratio = (white, r_white) if r_white >= r_black else (black, r_black)
    logger.warning("Kontrast hedefi (%.1f) karşılanamadı: %s -> %s (%.2f)", target, color, best, best_ratio)
    return best, best_ratio, False


def _best_foreground(background: str) -> str:
    rgb = hex_to_rgb(background)
    white = contrast_ratio((1.0, 1.0, 1.0), rgb)
    black = contrast_ratio((0.0, 0.0, 0.0), rgb)
    return "#ffffff" if white >= black else "#000000"


def _shift_l(hex_color: str, delta: float) -> str:
    l, c, h = _to_lch(hex_color)
    return _from_lch((min(1.0, max(0.0, l + delta)), c, h))


def _clamp_l(hex_color: str, low: float, high: float) -> str:
    l, c, h = _to_lch(hex_color)
    return _from_lch((min(high, max(low, l)), c, h))


def _damp(hex_color: str) -> str:
    l, c, h = _to_lch(hex_color)
    if c > 0.2:
        return _from_lch((l, c * 0.85, h))
    return hex_color


def _invert(hex_color: str) -> str:
    l, c, h = _to_lch(hex_color)
    return _damp(_from_lch((1.0 - l, c, h)))


def _derive_counter(base: dict[str, str], target_mode: ThemeMode) -> dict[str, str]:
    """Taramada yakalanmayan karşı tema için renkleri türetir (kontrast kontrolünden önce)."""
    if target_mode == "dark":
        bg_band, surface_band = (0.12, 0.16), (0.18, 0.22)
    else:
        bg_band, surface_band = (0.97, 0.99), (0.93, 0.96)
    return {
        "background": _clamp_l(base["background"], *bg_band),
        "surface": _clamp_l(base["surface"], *surface_band),
        "text_primary": _invert(base["text_primary"]),
        "text_muted": _invert(base["text_muted"]),
        "border": _invert(base["border"]),
        "accent": _damp(base["accent"]),
    }


def _fmt_num(value: float) -> str:
    value = round(value, 2)
    return str(int(value)) if value == int(value) else str(value)


_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?"
_MATRIX_RE = re.compile(rf"^matrix\(\s*({_NUM}(?:\s*,\s*{_NUM}){{5}})\s*\)$", re.I)
_MATRIX3D_RE = re.compile(rf"^matrix3d\(\s*({_NUM}(?:\s*,\s*{_NUM}){{15}})\s*\)$", re.I)
_PX_RE = re.compile(r"(-?\d*\.?\d+)px")
_EPS = 1e-6


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= _EPS


def _compose(sx: float, sy: float, tx: float, ty: float, tz: float = 0.0, three_d: bool = False) -> str | None:
    parts: list[str] = []
    if not (_close(tx, 0) and _close(ty, 0)):
        fn = "translate3d" if three_d else "translate"
        tail = f", {_fmt_num(tz)}px" if three_d else ""
        parts.append(f"{fn}({_fmt_num(tx)}px, {_fmt_num(ty)}px{tail})")
    if _close(sx, sy):
        if not _close(sx, 1):
            parts.append(f"scale({_fmt_num(sx)})")
    else:
        parts.append(f"scale({_fmt_num(sx)}, {_fmt_num(sy)})")
    return " ".join(parts) if parts else None


def _fmt_transform(raw: str | None) -> str | None:
    """matrix()/matrix3d() -> okunur translate/scale; döndürme/eğme içerenler ham kalır."""
    if not raw or raw.strip() == "none":
        return None
    text = raw.strip()
    m = _MATRIX_RE.match(text)
    if m:
        a, b, c, d, tx, ty = (float(v) for v in m.group(1).split(","))
        if _close(b, 0) and _close(c, 0) and a > 0 and d > 0:
            return _compose(a, d, tx, ty)
        return raw
    m = _MATRIX3D_RE.match(text)
    if m:
        v = [float(x) for x in m.group(1).split(",")]
        # sütun-öncelikli: [a b 0 0, c d 0 0, 0 0 1 0, tx ty tz 1]
        identity_rest = (
            _close(v[1], 0) and _close(v[2], 0) and _close(v[3], 0) and _close(v[4], 0)
            and _close(v[6], 0) and _close(v[7], 0) and _close(v[8], 0) and _close(v[9], 0)
            and _close(v[10], 1) and _close(v[11], 0) and _close(v[15], 1)
            and v[0] > 0 and v[5] > 0
        )
        if identity_rest:
            return _compose(v[0], v[5], v[12], v[13], v[14], three_d=not _close(v[14], 0))
        return raw
    return raw


def _scale_shadow(shadow: str, factor: float) -> str:
    if shadow == "none":
        return shadow
    return _PX_RE.sub(lambda m: f"{_fmt_num(float(m.group(1)) * factor)}px", shadow)


def _shadow_magnitude(shadow: str) -> float:
    return sum(abs(float(v)) for v in _PX_RE.findall(shadow))


def _with_generic(stack: str, family: str, mono: bool = False) -> str:
    text = stack.strip() or family
    lowered = [p.strip().strip("'\"").lower() for p in text.split(",")]
    if lowered and lowered[-1] in _GENERIC_FAMILIES:
        return text
    return f"{text}, {'monospace' if mono else 'sans-serif'}"


# --------------------------------------------------------------------------- tema renkleri


class _Themes:
    """Tema birleştirme sırasında kontrast düzeltmelerini ve uyarıları biriktirir."""

    def __init__(self) -> None:
        self.fixes: list[ContrastFix] = []
        self.warnings: list[str] = []

    def _fix(
        self,
        theme: ThemeMode,
        role: str,
        color: str,
        against_names: list[str],
        against: list[str],
        target: float,
    ) -> str:
        adjusted, ratio, achieved = ensure_contrast(color, against, target)
        if adjusted != color.lower() or not achieved:
            self.fixes.append(
                ContrastFix(
                    theme=theme,
                    role=role,
                    against=",".join(against_names),
                    original=color.lower(),
                    adjusted=adjusted,
                    ratio_before=round(_min_ratio(color, against), 4),
                    ratio_after=round(ratio, 4),
                    target=target,
                    achieved=achieved,
                )
            )
            if not achieved:
                self.warnings.append(
                    f"{theme} temasında '{role}' kontrast hedefine ({target}:1) ulaşamadı; "
                    f"en yakın değer {adjusted} ({ratio:.2f}:1) seçildi."
                )
        return adjusted

    def _neutral_accent(self, mode: ThemeMode, accent: str, bg: str) -> str:
        """Siyah-beyaz sitelerin vurgusu (örn. koyu temada beyaz buton) zıt temaya
        aynen taşınınca zeminde kaybolur. Renksiz (C < 0.03) ve zeminden ayrışmayan
        (< 3:1) vurgunun L değeri ters çevrilir; renkli vurgulara dokunulmaz (D19)."""
        l, c, h = _to_lch(accent)
        before = _min_ratio(accent, [bg])
        if c >= NEUTRAL_ACCENT_MAX_CHROMA or before >= 3.0:
            return accent
        flipped = _from_lch((1.0 - l, c, h))
        after = _min_ratio(flipped, [bg])
        if after <= before:
            return accent
        self.fixes.append(
            ContrastFix(
                theme=mode,
                role="accent",
                against="background",
                original=accent,
                adjusted=flipped,
                ratio_before=round(before, 4),
                ratio_after=round(after, 4),
                target=3.0,
                achieved=after >= 3.0,
            )
        )
        return flipped

    def finalize(self, mode: ThemeMode, c: dict[str, str]) -> ThemeColors:
        bg, surface = c["background"].lower(), c["surface"].lower()
        bs, bs_names = [bg, surface], ["background", "surface"]
        text_primary = self._fix(mode, "text-primary", c["text_primary"], bs_names, bs, 4.5)
        text_muted = self._fix(mode, "text-muted", c["text_muted"], bs_names, bs, 4.5)
        border = self._fix(mode, "border", c["border"], bs_names, bs, 3.0)
        accent = self._neutral_accent(mode, c["accent"].lower(), bg)
        accent_fg = _best_foreground(accent)
        ring = self._fix(mode, "ring", accent, bs_names, bs, 3.0)
        secondary = _shift_l(surface, -0.04 if mode == "light" else 0.04)
        secondary_fg = self._fix(mode, "secondary-foreground", text_primary, ["secondary"], [secondary], 4.5)
        destructive = self._fix(mode, "destructive", _DESTRUCTIVE[mode], bs_names, bs, 3.0)
        return ThemeColors(
            background=bg,
            surface=surface,
            text_primary=text_primary,
            text_muted=text_muted,
            accent=accent,
            accent_foreground=accent_fg,
            border=border,
            secondary=secondary,
            secondary_foreground=secondary_fg,
            destructive=destructive,
            destructive_foreground=_best_foreground(destructive),
            ring=ring,
        )


def _role_hexes(ex: SiteExtraction, accent_from: SiteExtraction) -> dict[str, str]:
    r = ex.colors.roles
    return {
        "background": r.background.hex,
        "surface": r.surface.hex,
        "text_primary": r.text_primary.hex,
        "text_muted": r.text_muted.hex,
        "border": r.border.hex,
        "accent": accent_from.colors.roles.accent.hex,
    }


# --------------------------------------------------------------------------- bileşenler


_FALLBACK_CHAIN = {
    "button": ("button", "input", "card"),
    "input": ("input", "button", "card"),
    "card": ("card", "button", "input"),
}
_DEFAULT_PADDING = {
    "button": (8.0, 16.0, 8.0, 16.0),
    "input": (8.0, 12.0, 8.0, 12.0),
    "card": (16.0, 16.0, 16.0, 16.0),
}


def _pick_style(ex: SiteExtraction, kind: str) -> tuple[ComponentStyle | None, bool]:
    """(stil, doğrudan_mı). Eksikse aynı kaynağın diğer bileşenlerinden türetir."""
    for i, name in enumerate(_FALLBACK_CHAIN[kind]):
        style = getattr(ex.components, name)
        if style is not None:
            return style, i == 0
    return None, False


def _component_spec(
    kind: str,
    radius_ex: SiteExtraction,
    body_ex: SiteExtraction,
    shadow_style: str,
    shadow_sm: str,
) -> ComponentSpec:
    """Radius `radius_ex` kaynağından, diğer karakter `body_ex` kaynağından gelir."""
    radius_style, _ = _pick_style(radius_ex, kind)
    style, direct = _pick_style(body_ex, kind)
    radius = quantize_radius(radius_style.border_radius_px) if radius_style else 8.0
    if style is None:
        width = 0.0 if kind == "card" else 1.0
        shadow = "none"
        padding = _DEFAULT_PADDING[kind]
        return ComponentSpec(
            radius_px=radius,
            border_width_px=width,
            border_style="solid" if width else "none",
            shadow=shadow,
            padding=padding,
            source=body_ex.source,
        )
    width = style.border_width_px
    if not direct and kind == "input":
        width = max(1.0, width)
    border_style = style.border_style if width > 0 else "none"
    if width > 0 and border_style == "none":
        border_style = "solid"
    if direct:
        shadow = style.box_shadow
    elif kind == "card":
        shadow = shadow_sm
    else:
        shadow = "none"
    if shadow_style == "none":
        shadow = "none"
    padding = tuple(quantize_spacing(p) for p in style.padding)
    stats: ComponentStats | None = style.stats if direct else None
    hover: HoverStyle | None = style.hover if direct else None
    if hover is not None:
        hover = hover.model_copy(update={"transform": _fmt_transform(hover.transform)})
    return ComponentSpec(
        radius_px=radius,
        border_width_px=width,
        border_style=border_style,
        shadow=shadow,
        padding=padding,  # type: ignore[arg-type]
        backdrop_filter=style.backdrop_filter if direct else "none",
        hover=hover,
        stats=stats,
        source=body_ex.source,
    )


# --------------------------------------------------------------------------- blend


def _hover_of(ex: SiteExtraction) -> HoverStyle | None:
    for name in ("button", "input", "card"):
        style = getattr(ex.components, name)
        if style is not None and style.hover is not None:
            return style.hover
    return None


def _motion(ex: SiteExtraction) -> MotionSystem:
    hover = _hover_of(ex)
    if hover is None:
        return MotionSystem(
            duration_ms=150.0,
            easing="ease",
            hover_transform=None,
            hover_description="Belirgin bir hover değişikliği yakalanmadı",
            measured=False,
        )
    transform = _fmt_transform(hover.transform)
    parts: list[str] = []
    if transform:
        parts.append(transform)
    if hover.background_changes:
        parts.append("arka plan rengi değişir")
    if hover.border_changes:
        parts.append("kenarlık rengi değişir")
    if hover.shadow_changes:
        parts.append("gölge değişir")
    return MotionSystem(
        duration_ms=hover.duration_ms,
        easing=hover.easing or "ease",
        hover_transform=transform,
        hover_description=" + ".join(parts) if parts else "Belirgin bir hover değişikliği yok",
    )


def _layout(ex: SiteExtraction) -> LayoutSystem:
    observed = sorted(set(ex.layout.breakpoints))
    chosen: dict[str, float] = {}
    for value in observed:
        if value < 480 or value > 1800:
            continue
        key, std = min(_BREAKPOINT_KEYS, key=lambda kv: (abs(kv[1] - value), kv[1]))
        if key not in chosen or abs(value - std) < abs(chosen[key] - std):
            chosen[key] = value
    breakpoints: dict[str, float] = {}
    prev = 0.0
    for key, std in _BREAKPOINT_KEYS:
        value = chosen.get(key, std)
        if value <= prev:
            value = max(std, prev + 1)
        breakpoints[key] = float(value)
        prev = value
    return LayoutSystem(
        container_max_width=float(ex.layout.container_max_width or 1200.0),
        container_measured=bool(ex.layout.container_max_width),
        grid_measured=bool(ex.layout.grid_columns),
        breakpoints=breakpoints,
        grid_columns=int(ex.layout.grid_columns[0]) if ex.layout.grid_columns else 12,
    )


def _shadow_system(ex: SiteExtraction) -> ShadowSystem:
    style = ex.components.shadow_style
    if style == "none":
        return ShadowSystem(style="none", sm="none", md="none", lg="none")
    observed = sorted(
        {s for s in ex.components.shadows if s and s != "none"},
        key=lambda s: (_shadow_magnitude(s), s),
    )
    if len(observed) >= 3:
        return ShadowSystem(style=style, sm=observed[0], md=observed[len(observed) // 2], lg=observed[-1])
    base: str | None = None
    for name in ("card", "button", "input"):
        comp = getattr(ex.components, name)
        if comp is not None and comp.box_shadow and comp.box_shadow != "none":
            base = comp.box_shadow
            break
    if base is None and observed:
        base = observed[0]
    if base is None:
        base = {
            "hard": "4px 4px 0px 0px rgb(0, 0, 0)",
            "layered": "0px 4px 6px -1px rgba(0, 0, 0, 0.1), 0px 2px 4px -2px rgba(0, 0, 0, 0.1)",
        }.get(style, "0px 4px 12px 0px rgba(0, 0, 0, 0.1)")
    return ShadowSystem(
        style=style,
        sm=_scale_shadow(base, 0.5),
        md=base,
        lg=_scale_shadow(base, 1.75),
    )


def _typography(
    body_ex: SiteExtraction,
    display_ex: SiteExtraction,
    all_by_weight: list[SiteExtraction],
) -> TypographySystem:
    bt = body_ex.typography
    dt = display_ex.typography

    sans = FontSpec(
        family=bt.body_family,
        stack=_with_generic(bt.body_stack, bt.body_family),
        source=body_ex.source,
    )
    display = FontSpec(
        family=dt.display_family,
        stack=_with_generic(dt.display_stack, dt.display_family),
        source=display_ex.source,
    )
    mono_ex = None
    if bt.mono_family:
        mono_ex = body_ex
    else:
        for ex in all_by_weight:
            if ex.typography.mono_family:
                mono_ex = ex
                break
    if mono_ex is not None:
        mt = mono_ex.typography
        family = mt.mono_family or "ui-monospace"
        mono = FontSpec(
            family=family,
            stack=_with_generic(mt.mono_stack or family, family, mono=True),
            source=mono_ex.source,
        )
    else:
        mono = FontSpec(family="ui-monospace", stack=_DEFAULT_MONO_STACK, source=body_ex.source)

    base = bt.base_size_px or 16.0
    ratio = bt.scale_ratio
    names = (("xs", -2), ("sm", -1), ("base", 0), ("lg", 1), ("xl", 2), ("2xl", 3), ("3xl", 4), ("4xl", 5), ("5xl", 6))
    sizes = {k: round(base * ratio**n, 2) for k, n in names}

    para = bt.styles.get("p")
    normal_lh = para.line_height if para and 1.2 <= para.line_height <= 2.0 else 1.5
    heading = dt.styles.get("h1") or dt.styles.get("h2")
    tight_lh = heading.line_height if heading and 0.9 <= heading.line_height <= 1.4 else 1.2
    tight_lh = min(tight_lh, normal_lh - 0.1)
    line_heights = {
        "tight": round(tight_lh, 2),
        "normal": round(normal_lh, 2),
        "relaxed": round(normal_lh + 0.2, 2),
    }

    normal_w = para.font_weight if para and para.font_weight in (300, 400) else 400
    bold_w = heading.font_weight if heading and heading.font_weight >= 700 else 700
    weights = {"normal": int(normal_w), "medium": 500, "semibold": 600, "bold": int(bold_w)}

    tight_ls = heading.letter_spacing_em if heading and heading.letter_spacing_em < 0 else -0.02
    letter_spacing = {
        "tight": round(min(-0.005, max(-0.05, tight_ls)), 3),
        "normal": 0.0,
        "wide": 0.05,
    }

    imports: list[str] = []
    for ex in (body_ex, display_ex, mono_ex or body_ex):
        for link in ex.typography.font_links:
            if link not in imports:
                imports.append(link)

    return TypographySystem(
        sans=sans,
        mono=mono,
        display=display,
        base_size_px=base,
        scale_ratio=ratio,
        sizes=sizes,
        line_heights=line_heights,
        weights=weights,
        letter_spacing=letter_spacing,
        font_imports=imports,
    )


def _radius_dict(control_ex: SiteExtraction, card_ex: SiteExtraction) -> dict[str, float]:
    button, _ = _pick_style(control_ex, "button")
    card, _ = _pick_style(card_ex, "card")
    r = quantize_radius(button.border_radius_px) if button else 8.0
    c = quantize_radius(card.border_radius_px) if card else r
    capped = min(r, 24.0)
    sm = quantize_radius(capped / 2)
    lg = max(r, quantize_radius(max(c, capped * 1.5)))
    lg = max(lg, sm)
    xl = max(lg, quantize_radius(lg * 1.5 if lg < 9999 else lg))
    return {"none": 0.0, "sm": sm, "md": r, "lg": lg, "xl": xl, "full": 9999.0, "default": r}


def _spacing_dict(ex: SiteExtraction) -> dict[str, float]:
    values = sorted({quantize_spacing(v) for v in ex.spacing.scale} | {0.0})
    return {str(i): v for i, v in enumerate(values)}


def blend(
    extractions: list[SiteExtraction], weights: list[float | None] | None = None
) -> tuple[DesignSystem, BlendReport]:
    if not extractions:
        raise DesignDNAError("Harmanlama için en az bir kaynak gerekli.")
    n = len(extractions)
    if weights is None:
        weights = [None] * n
    if len(weights) != n:
        raise DesignDNAError("Ağırlık sayısı kaynak sayısıyla eşleşmiyor.")
    norm = normalize_weights(list(weights))
    order = sorted(range(n), key=lambda i: (-norm[i], i))
    eligible_idx = [i for i in order if norm[i] >= ELIGIBILITY_THRESHOLD - _EPS]
    if not eligible_idx:
        eligible_idx = [order[0]]
    elif eligible_idx[0] != order[0]:  # pragma: no cover - sıralama gereği olmaz
        eligible_idx.insert(0, order[0])

    warnings: list[str] = []
    for i in order:
        if i not in eligible_idx:
            warnings.append(
                f"Kaynak '{extractions[i].source}' ağırlığı %{norm[i] * 100:.1f}, "
                f"%{ELIGIBILITY_THRESHOLD * 100:.0f} eşiğinin altında; hiçbir rol almadı, "
                "roller baskın kaynağa düştü."
            )

    g1 = eligible_idx[0]
    g2 = eligible_idx[1] if len(eligible_idx) > 1 else g1
    g3 = eligible_idx[2] if len(eligible_idx) > 2 else g2
    role_source: dict[str, int] = {}
    reasons: dict[str, str] = {}
    for group, roles, src in (("1", GROUP1, g1), ("2", GROUP2, g2), ("3", GROUP3, g3)):
        for role in roles:
            role_source[role] = src
            pct = norm[src] * 100
            if group == "1":
                why = f"Grup 1: baskın kaynak (%{pct:.0f})"
            else:
                rank = int(group)
                if eligible_idx.index(src) + 1 == rank:
                    why = f"Grup {group}: {rank}. kaynak (%{pct:.0f})"
                else:
                    why = (
                        f"Grup {group}: {rank}. uygun kaynak yok; "
                        f"{eligible_idx.index(src) + 1}. kaynağa (%{pct:.0f}) düştü"
                    )
            reasons[role] = why
    ineligible_note = " (eşik altı kaynak(lar) nedeniyle baskın kaynak seçildi)"
    if len(eligible_idx) < n:
        for role in ROLE_ORDER:
            if role_source[role] == g1 and role not in GROUP1:
                reasons[role] += ineligible_note

    by_weight = [extractions[i] for i in order]
    e1, e2, e3 = extractions[g1], extractions[g2], extractions[g3]

    # --- renk temaları
    base_mode: ThemeMode = e1.natural_mode
    other_mode: ThemeMode = "dark" if base_mode == "light" else "light"
    base_colors = _role_hexes(e1, e2)
    themes = _Themes()
    base_theme = themes.finalize(base_mode, base_colors)

    counter_kind = "derived"
    counter_colors = _derive_counter(base_colors, other_mode)
    if e1.counter is not None and e1.counter.mode != base_mode:
        counter_kind = "captured"
        cr = e1.counter.colors
        counter_colors = {
            "background": cr.background.hex,
            "surface": cr.surface.hex,
            "text_primary": cr.text_primary.hex,
            "text_muted": cr.text_muted.hex,
            "border": cr.border.hex,
            "accent": cr.accent.hex if g2 == g1 else base_colors["accent"],
        }
    counter_theme = themes.finalize(other_mode, counter_colors)
    light = base_theme if base_mode == "light" else counter_theme
    dark = counter_theme if base_mode == "light" else base_theme

    # --- tipografi, gölge, hareket, layout, bileşenler
    typography = _typography(e1, e3, by_weight)
    shadows = _shadow_system(e3)
    components = ComponentSystem(
        button=_component_spec("button", e2, e2, shadows.style, shadows.sm),
        input=_component_spec("input", e2, e2, shadows.style, shadows.sm),
        card=_component_spec("card", e3, e3, shadows.style, shadows.sm),
    )
    gradients = [g.value for g in sorted(e1.colors.gradients, key=lambda g: (-g.weight, g.value))[:3]]

    source_refs = []
    for i, ex in enumerate(extractions):
        roles = [r for r in ROLE_ORDER if role_source[r] == i] if i in eligible_idx else []
        source_refs.append(SourceRef(source=ex.source, weight=norm[i], natural_mode=ex.natural_mode, roles=roles))

    design = DesignSystem(
        tool_version=__version__,
        sources=source_refs,
        base_mode=base_mode,
        light=light,
        dark=dark,
        gradients=gradients,
        typography=typography,
        spacing=_spacing_dict(e1),
        spacing_base=e1.spacing.base,
        radius=_radius_dict(e2, e3),
        shadows=shadows,
        motion=_motion(e2),
        layout=_layout(e1),
        components=components,
    )

    report = BlendReport(
        tool_version=__version__,
        sources=[
            SourceWeight(
                source=ex.source,
                input_weight=weights[i],
                normalized_weight=norm[i],
                eligible=i in eligible_idx,
            )
            for i, ex in enumerate(extractions)
        ],
        roles=[
            RoleAssignment(role=r, source=extractions[role_source[r]].source, reason=reasons[r])
            for r in ROLE_ORDER
        ],
        contrast_fixes=themes.fixes,
        counter_theme=counter_kind,  # type: ignore[arg-type]
        warnings=warnings + themes.warnings,
    )
    return design, report
