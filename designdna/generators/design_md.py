"""DESIGN.md: veriye dayalı kurallar + bağlam. Üst sınır 300 satır (yapısal olarak garanti)."""

from __future__ import annotations

import re

from designdna.models import DesignSystem

from ._common import (
    COLOR_ROLES, kebab, num, px, render, sorted_sizes, sorted_spacing,
)

MAX_LINES = 300
MAX_SOURCES = 20
MAX_RULES = 16


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def build_rules(ds: DesignSystem) -> list[dict[str, str]]:
    """Her kural {kind: Do|Don't, text, evidence}; kanıtı olmayan kural üretilmez."""
    rules: list[dict[str, str]] = []

    def add(kind: str, text: str, evidence: str) -> None:
        if re.search(r"\d", evidence):
            rules.append({"kind": kind, "text": text, "evidence": evidence})

    for name in ("button", "input", "card"):
        spec = getattr(ds.components, name)
        st = spec.stats
        if st is None or st.count <= 0:
            continue
        n = st.count
        if st.with_border >= 0.5 and spec.border_width_px > 0:
            add("Do", f"Give {name}s a {px(spec.border_width_px)} {spec.border_style} border (`--color-border`)",
                f"{_pct(st.with_border)} of {n} sampled {name}s have a border")
        elif st.with_border <= 0.2:
            add("Don't", f"Don't add borders to {name}s",
                f"{_pct(st.with_border)} of {n} sampled {name}s have a border")
        if st.with_shadow >= 0.5 and spec.shadow != "none":
            add("Do", f"Use `{spec.shadow}` on {name}s",
                f"{_pct(st.with_shadow)} of {n} sampled {name}s have a shadow")
        elif st.with_shadow <= 0.2:
            add("Don't", f"Don't put drop shadows on {name}s",
                f"{_pct(st.with_shadow)} of {n} sampled {name}s have a shadow")
        if st.with_backdrop >= 0.5 and spec.backdrop_filter != "none":
            add("Do", f"Apply `backdrop-filter: {spec.backdrop_filter}` to {name}s",
                f"{_pct(st.with_backdrop)} of {n} sampled {name}s use a backdrop filter")
        total = sum(st.radius_values.values())
        if total > 0:
            k, v = sorted(st.radius_values.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            add("Do", f"Round {name}s with {k}px corners",
                f"{v} of {total} ({_pct(v / total)}) sampled {name}s use a {k}px radius")

    sh = ds.shadows
    if sh.style == "none":
        total = sum(c.stats.count for c in (ds.components.button, ds.components.input, ds.components.card) if c.stats)
        add("Don't", "Don't introduce shadows; separate surfaces with borders and color",
            f"shadow style classified as `none` across {total} sampled components")
    else:
        add("Do", f"Keep a {sh.style} shadow character; elevate with `--shadow-sm/md/lg`",
            f"shadow style classified `{sh.style}`; md = `{sh.md}`")

    btn = ds.components.button
    h = btn.hover
    if h is not None and h.samples > 0:
        if h.transform:
            add("Do", f"On button hover apply `{h.transform}`",
                f"transform observed in {h.samples} hover-probed buttons")
        else:
            add("Don't", "Don't move or scale buttons on hover",
                f"0 of {h.samples} hover-probed buttons changed transform")
        if h.shadow_changes:
            add("Do", "Change the shadow on button hover", f"shadow changed in {h.samples} hover-probed buttons")
    if ds.motion.duration_ms > 0:
        add("Do", f"Transition with `{num(ds.motion.duration_ms)}ms {ds.motion.easing}`",
            f"dominant transition duration measured at {num(ds.motion.duration_ms)}ms")
    if ds.spacing:
        mx = max(ds.spacing.values())
        add("Do", f"Space elements in multiples of {ds.spacing_base}px (`--spacing-*`)",
            f"{len(ds.spacing)} scale steps on a {ds.spacing_base}px grid, up to {num(mx)}px")
    add("Do", f"Constrain page content to {num(ds.layout.container_max_width)}px",
        f"container max-width measured at {num(ds.layout.container_max_width)}px, {ds.layout.grid_columns}-column grids")
    return rules[:MAX_RULES]


def _component_examples(ds: DesignSystem) -> dict[str, str]:
    b, i, c = ds.components.button, ds.components.input, ds.components.card

    def pad(p: tuple[float, float, float, float]) -> str:
        return f"px-[{num(p[1])}px] py-[{num(p[0])}px]"

    def border(w: float) -> str:
        return f"border-[{num(w)}px] border-[var(--color-border)]" if w > 0 else "border-0"

    hover = ""
    if b.hover and b.hover.transform:
        hover = " hover:[transform:" + b.hover.transform.replace(" ", "") + "]"
    elif b.hover:
        hover = " hover:brightness-95"
    dur = f"duration-[{num(ds.motion.duration_ms)}ms]"
    shadow_b = "shadow-[var(--shadow-sm)] " if b.shadow != "none" else ""
    shadow_c = "shadow-[var(--shadow-md)] " if c.shadow != "none" else ""
    return {
        "button": (f'<button class="inline-flex items-center {pad(b.padding)} rounded-[{num(b.radius_px)}px] '
                   f'{border(b.border_width_px)} {shadow_b}bg-[var(--color-accent)] text-[var(--color-accent-foreground)] '
                   f'font-medium transition {dur}{hover} disabled:opacity-50">Action</button>'),
        "input": (f'<input class="w-full {pad(i.padding)} rounded-[{num(i.radius_px)}px] {border(i.border_width_px)} '
                  f'bg-[var(--color-surface)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] '
                  f'focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]" placeholder="Label">'),
        "card": (f'<div class="p-[{num(c.padding[0])}px] rounded-[{num(c.radius_px)}px] {border(c.border_width_px)} '
                 f'{shadow_c}bg-[var(--color-surface)] text-[var(--color-text-primary)]">'
                 f'<h3 class="font-semibold">Title</h3><p class="text-[var(--color-text-muted)]">Body</p></div>'),
        "navbar": (f'<nav class="flex items-center justify-between {pad(b.padding)} border-b-[{num(max(c.border_width_px, 1))}px] '
                   f'border-[var(--color-border)] bg-[var(--color-background)]"><span class="font-semibold">Brand</span>'
                   f'<a class="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]" href="#">Link</a></nav>'),
        "hero": (f'<section class="mx-auto max-w-[{num(ds.layout.container_max_width)}px] py-[{num(ds.spacing.get("7", 96))}px] text-center">'
                 f'<h1 class="text-[{num(ds.typography.sizes.get("5xl", 48))}px] font-bold tracking-tight '
                 f'text-[var(--color-text-primary)]">Headline</h1>'
                 f'<p class="mt-4 text-[var(--color-text-muted)]">Supporting text</p></section>'),
    }


def render_design_md(ds: DesignSystem) -> str:
    sources = ds.sources[:MAX_SOURCES]
    ctx = dict(
        ds=ds,
        sources=[
            {"source": s.source, "weight": _pct(s.weight), "mode": s.natural_mode, "roles": ", ".join(s.roles) or "-"}
            for s in sources
        ],
        more_sources=max(0, len(ds.sources) - MAX_SOURCES),
        color_rows=[
            {"role": kebab(r), "light": getattr(ds.light, r), "dark": getattr(ds.dark, r)} for r in COLOR_ROLES
        ],
        sizes=[(k, num(v)) for k, v in sorted_sizes(ds)],
        spacing=[(k, num(v)) for k, v in sorted_spacing(ds)],
        radius=[(k, num(v)) for k, v in sorted(ds.radius.items(), key=lambda kv: (kv[1], kv[0]))],
        rules=build_rules(ds),
        ex=_component_examples(ds),
        num=num,
    )
    text = render("DESIGN.md.j2", **ctx)
    lines = text.split("\n")
    if len(lines) > MAX_LINES:  # yapısal emniyet: şablon sabit satırlı, kaynaklar ve kurallar kısıtlı
        text = "\n".join(lines[: MAX_LINES - 1]) + "\n"
    return text
