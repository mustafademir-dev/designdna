"""Bileşen (buton/input/kart) sezgisel tespiti ve madenciliği — saf Python."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from designdna.models import (
    ComponentStats,
    Components,
    ComponentStyle,
    ComponentType,
    ElementRecord,
    HoverDiff,
    HoverStyle,
    RawSnapshot,
    ShadowStyle,
)
from designdna.utils.color_math import RGB, composite, delta_e_ok, parse_color, rgb_to_hex

_INPUT_TYPES = {"text", "email", "search", "password", "url", "tel", "number"}
_BUTTON_INPUT_TYPES = {"button", "submit", "reset"}
_CARD_EXCLUDED_TAGS = {
    "html", "body", "header", "nav", "footer", "tr", "td", "th", "table", "thead", "tbody",
    "svg", "img", "picture", "video", "canvas", "option", "label", "pre", "code", "kbd", "samp",
}
_WHITE: RGB = (1.0, 1.0, 1.0)
_PX_RE = re.compile(r"^(-?(?:\d+\.?\d*|\.\d+))(px|%)?$")
_NUM_RE = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)(?:px)?$")
_CARD_MIN_AREA = 4000.0
_BORDER_SIDES = ("top", "right", "bottom", "left")


# --------------------------------------------------------------------------- parsing helpers


def _px(value: str | None) -> float:
    if not value:
        return 0.0
    m = _PX_RE.match(value.strip())
    if not m or m.group(2) == "%":
        return 0.0
    return float(m.group(1))


def _split_top(text: str, sep: str | None) -> list[str]:
    """Parantez dışındaki ayırıcıya göre böler (sep None -> boşluk)."""
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        split = depth == 0 and (ch.isspace() if sep is None else ch == sep)
        if split:
            if cur:
                parts.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


@dataclass(frozen=True)
class _Shadow:
    raw: str
    inset: bool
    x: float
    y: float
    blur: float
    spread: float
    alpha: float

    @property
    def visible(self) -> bool:
        return self.alpha > 0 and not (self.x == 0 and self.y == 0 and self.blur == 0 and self.spread == 0)

    @property
    def ring(self) -> bool:
        return self.x == 0 and self.y == 0 and self.blur == 0


def parse_shadows(value: str | None) -> list[_Shadow]:
    """box-shadow değerini katmanlara ayırır (Chrome: renk önce; virgüller rgba() içinde olabilir)."""
    if not value or value.strip().lower() == "none":
        return []
    layers: list[_Shadow] = []
    for raw in _split_top(value, ","):
        tokens = _split_top(raw, None)
        inset = any(t.lower() == "inset" for t in tokens)
        nums: list[float] = []
        alpha = 1.0
        for t in tokens:
            if t.lower() == "inset":
                continue
            if _NUM_RE.match(t):
                nums.append(float(t.removesuffix("px")))
                continue
            c = parse_color(t)
            if c is not None:
                alpha = c[3]
        if len(nums) < 2:
            continue
        nums += [0.0] * (4 - len(nums))
        layers.append(_Shadow(raw, inset, nums[0], nums[1], nums[2], nums[3], alpha))
    return layers


# --------------------------------------------------------------------------- snapshot context


class _Context:
    def __init__(self, snapshot: RawSnapshot) -> None:
        self.snapshot = snapshot
        self.by_idx: dict[int, ElementRecord] = {e.idx: e for e in snapshot.elements}
        self._eff: dict[int, RGB] = {}
        self.has_text_desc: dict[int, bool] = {}
        for el in reversed(snapshot.elements):
            own = el.text_length > 0 or (len(el.tag) == 2 and el.tag[0] == "h" and el.tag[1] in "123456")
            if (own or self.has_text_desc.get(el.idx, False)) and el.parent_idx is not None:
                self.has_text_desc[el.parent_idx] = True

    def effective_bg(self, idx: int | None) -> RGB:
        if idx is None:
            return _WHITE
        chain: list[ElementRecord] = []
        cur: int | None = idx
        while cur is not None and cur not in self._eff:
            el = self.by_idx.get(cur)
            if el is None:
                break
            chain.append(el)
            cur = el.parent_idx
        base = self._eff[cur] if cur is not None and cur in self._eff else _WHITE
        for el in reversed(chain):
            c = parse_color(el.styles.get("background-color", ""))
            if c is not None and c[3] > 0:
                base = composite(c, base)
            self._eff[el.idx] = base
        return self._eff[idx] if idx in self._eff else base


_CTX_CACHE: list[_Context] = []


def _context(snapshot: RawSnapshot) -> _Context:
    for ctx in _CTX_CACHE:
        if ctx.snapshot is snapshot:
            return ctx
    ctx = _Context(snapshot)
    _CTX_CACHE.append(ctx)
    if len(_CTX_CACHE) > 4:
        _CTX_CACHE.pop(0)
    return ctx


# --------------------------------------------------------------------------- element facts


def _own_bg_alpha(el: ElementRecord) -> float:
    c = parse_color(el.styles.get("background-color", ""))
    return c[3] if c else 0.0


def _border_info(el: ElementRecord, ctx: _Context) -> tuple[float, str, str | None]:
    """(genişlik, stil, hex renk) — en kalın görünür kenar; yoksa (0,'none',None)."""
    best: tuple[float, str, str | None] = (0.0, "none", None)
    bg = ctx.effective_bg(el.idx)
    for side in _BORDER_SIDES:
        w = _px(el.styles.get(f"border-{side}-width"))
        style = (el.styles.get(f"border-{side}-style") or "none").strip().lower()
        if w < 0.5 or style in ("none", "hidden"):
            continue
        col = parse_color(el.styles.get(f"border-{side}-color", ""))
        if col is not None and col[3] <= 0:
            continue
        hexc = rgb_to_hex(composite(col, bg)) if col is not None else None
        if w > best[0]:
            best = (round(w, 1), style, hexc)
    return best


def _visible_shadows(el: ElementRecord) -> list[_Shadow]:
    return [s for s in parse_shadows(el.styles.get("box-shadow")) if s.visible]


def _has_backdrop(el: ElementRecord) -> bool:
    v = (el.styles.get("backdrop-filter") or "none").strip().lower()
    return v not in ("", "none")


def _has_visible_bg(el: ElementRecord, ctx: _Context) -> bool:
    if _own_bg_alpha(el) <= 0:
        return False
    parent_bg = ctx.effective_bg(el.parent_idx)
    return delta_e_ok(ctx.effective_bg(el.idx), parent_bg) >= 0.02


def _radius_px(el: ElementRecord) -> float:
    best = 0.0
    w, h = el.bbox.width, el.bbox.height
    for corner in ("top-left", "top-right", "bottom-right", "bottom-left"):
        raw = (el.styles.get(f"border-{corner}-radius") or "0px").strip().split()[0]
        m = _PX_RE.match(raw)
        if not m:
            continue
        v = float(m.group(1))
        if m.group(2) == "%":
            v = v / 100.0 * min(w, h)
        best = max(best, v)
    return round(best, 1)


# --------------------------------------------------------------------------- classification


def classify_element(el: ElementRecord, snapshot: RawSnapshot) -> ComponentType | None:
    tag = el.tag.lower()
    role = (el.role or "").lower()
    itype = (el.input_type or "").lower()
    if tag == "button" or role == "button":
        return "button"
    if tag == "input" and itype in _BUTTON_INPUT_TYPES:
        return "button"
    if tag == "a" and any("btn" in c.lower() or "button" in c.lower() for c in el.classes):
        return "button"
    if tag == "textarea" or tag == "select":
        return "input"
    if tag == "input" and (not itype or itype in _INPUT_TYPES):
        return "input"
    if tag in _CARD_EXCLUDED_TAGS or tag == "input":
        return None
    ctx = _context(snapshot)
    if el.area < _CARD_MIN_AREA:
        return None
    vp = snapshot.viewport
    if el.bbox.width >= 0.9 * vp.width or el.area >= 0.5 * vp.width * vp.height:
        return None
    if not ctx.has_text_desc.get(el.idx, False):
        return None
    if (
        _has_visible_bg(el, ctx)
        or _border_info(el, ctx)[0] > 0
        or _visible_shadows(el)
        or (_has_backdrop(el) and _own_bg_alpha(el) > 0)
    ):
        return "card"
    return None


# --------------------------------------------------------------------------- aggregation


def _wmode(weights: Counter, default=None):
    """Ağırlıklı mod; eşitlikte str(anahtar) artan."""
    if not weights:
        return default
    return sorted(weights.items(), key=lambda kv: (-kv[1], str(kv[0])))[0][0]


def _fmt_px(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def _padding(el: ElementRecord) -> tuple[float, float, float, float]:
    return tuple(round(_px(el.styles.get(f"padding-{s}")), 1) for s in _BORDER_SIDES)  # type: ignore[return-value]


def _hover_style(hovers: list[HoverDiff]) -> HoverStyle | None:
    if not hovers:
        return None
    transforms = Counter(
        h.after.get("transform", "none")
        for h in hovers
        if "transform" in h.changed and (h.after.get("transform") or "none") != "none"
    )
    durations = Counter(h.transition_duration_ms for h in hovers)
    easings = Counter(h.transition_easing for h in hovers)
    return HoverStyle(
        samples=len(hovers),
        transform=_wmode(transforms),
        background_changes=any("background-color" in h.changed for h in hovers),
        border_changes=any("border-color" in h.changed for h in hovers),
        shadow_changes=any("box-shadow" in h.changed for h in hovers),
        duration_ms=_wmode(durations, 0.0),
        easing=_wmode(easings, "ease"),
    )


def _style_for(elements: list[ElementRecord], ctx: _Context, hovers: list[HoverDiff]) -> ComponentStyle:
    n = len(elements)
    radius_w: Counter = Counter()
    radius_counts: Counter = Counter()
    border_sig: dict[tuple[float, str], Counter] = {}
    border_sig_w: Counter = Counter()
    shadow_w: Counter = Counter()
    backdrop_w: Counter = Counter()
    padding_w: Counter = Counter()
    bg_w: Counter = Counter()
    fg_w: Counter = Counter()
    with_border = with_shadow = with_backdrop = with_bg = 0
    for el in elements:
        w = max(el.area, 1.0)
        r = _radius_px(el)
        radius_w[r] += w
        radius_counts[_fmt_px(r)] += 1
        bw, bs, bc = _border_info(el, ctx)
        sig = (bw, bs)
        border_sig_w[sig] += w
        border_sig.setdefault(sig, Counter())[bc] += w
        if bw > 0:
            with_border += 1
        shadows = [s for s in parse_shadows(el.styles.get("box-shadow")) if s.alpha > 0]
        raw = el.styles.get("box-shadow", "none").strip() if shadows else "none"
        shadow_w[raw] += w
        if shadows:
            with_shadow += 1
        bd = (el.styles.get("backdrop-filter") or "none").strip() or "none"
        backdrop_w[bd] += w
        if _has_backdrop(el):
            with_backdrop += 1
        padding_w[_padding(el)] += w
        if _has_visible_bg(el, ctx):
            with_bg += 1
        if _own_bg_alpha(el) > 0:
            bg_w[rgb_to_hex(ctx.effective_bg(el.idx))] += w
        fc = parse_color(el.styles.get("color", ""))
        if fc is not None:
            fg_w[rgb_to_hex(composite(fc, ctx.effective_bg(el.idx)))] += w
    sig = _wmode(border_sig_w, (0.0, "none"))
    border_color = _wmode(border_sig.get(sig, Counter())) if sig[0] > 0 else None
    return ComponentStyle(
        border_radius_px=_wmode(radius_w, 0.0),
        border_width_px=sig[0],
        border_style=sig[1] if sig[0] > 0 else "none",
        border_color=border_color,
        box_shadow=_wmode(shadow_w, "none"),
        backdrop_filter=_wmode(backdrop_w, "none"),
        padding=_wmode(padding_w, (0.0, 0.0, 0.0, 0.0)),
        background=_wmode(bg_w),
        foreground=_wmode(fg_w),
        stats=ComponentStats(
            count=n,
            with_border=with_border / n,
            with_shadow=with_shadow / n,
            with_backdrop=with_backdrop / n,
            with_background=with_bg / n,
            radius_values=dict(sorted(radius_counts.items(), key=lambda kv: (-kv[1], float(kv[0])))),
        ),
        hover=_hover_style(hovers),
    )


def _shadow_style(snapshot: RawSnapshot) -> tuple[ShadowStyle, list[str]]:
    votes: Counter[str] = Counter()
    raws: Counter[str] = Counter()
    for el in snapshot.elements:
        layers = [s for s in parse_shadows(el.styles.get("box-shadow")) if s.visible and not s.inset]
        if not layers:
            layers = [s for s in parse_shadows(el.styles.get("box-shadow")) if s.visible]
        if not layers:
            continue
        raws[el.styles["box-shadow"].strip()] += 1
        real = [s for s in layers if not s.ring] or []
        if not real:
            continue
        if real[0].blur == 0:
            votes["hard"] += 1
        elif len(real) > 1:
            votes["layered"] += 1
        else:
            votes["soft"] += 1
    shadows = [k for k, _ in sorted(raws.items(), key=lambda kv: (-kv[1], kv[0]))][:8]
    if not votes:
        return "none", shadows
    order = {"hard": 0, "layered": 1, "soft": 2}
    style = sorted(votes.items(), key=lambda kv: (-kv[1], order[kv[0]]))[0][0]
    return style, shadows  # type: ignore[return-value]


def mine_components(snapshot: RawSnapshot, hovers: list[HoverDiff]) -> Components:
    ctx = _context(snapshot)
    groups: dict[str, list[ElementRecord]] = {"button": [], "input": [], "card": []}
    for el in snapshot.elements:
        t = classify_element(el, snapshot)
        if t is not None:
            groups[t].append(el)
    # Kart sarmalayıcılarını ele: içinde >= 2 başka kart bulunan kart bir kapsayıcıdır.
    cards = groups["card"]
    if cards:
        card_ids = {c.idx for c in cards}
        nested: Counter[int] = Counter()
        for c in cards:
            p = c.parent_idx
            while p is not None:
                if p in card_ids:
                    nested[p] += 1
                p = ctx.by_idx[p].parent_idx if p in ctx.by_idx else None
        groups["card"] = [c for c in cards if nested[c.idx] < 2]
    shadow_style, shadows = _shadow_style(snapshot)
    styles: dict[str, ComponentStyle | None] = {}
    for kind, els in groups.items():
        if not els:
            styles[kind] = None
            continue
        styles[kind] = _style_for(els, ctx, [h for h in hovers if h.component_type == kind])
    return Components(
        button=styles["button"],
        input=styles["input"],
        card=styles["card"],
        shadow_style=shadow_style,
        shadows=shadows,
    )
