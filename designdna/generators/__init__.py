"""DesignDNA generators: DesignSystem -> CSS / JS / JSON / Markdown / HTML."""

from __future__ import annotations

from pathlib import Path

from designdna.models import BlendReport, DesignSystem, ThemeColors

from ._common import (
    COLOR_ROLES, css_safe, family_list, kebab, num, oklch_of, ratio, render,
    readable_transform, sorted_sizes, sorted_spacing,
)
from .design_md import render_design_md
from .tokens import render_tokens_json

OUTPUT_FILES = (
    "variables.css",
    "tailwind.config.js",
    "tailwind-v4.css",
    "shadcn-theme.css",
    "tokens.json",
    "DESIGN.md",
    "preview.html",
)

__all__ = [
    "OUTPUT_FILES", "generate_all", "write_blend_report", "render_variables_css",
    "render_tailwind_config", "render_tailwind_v4", "render_shadcn_theme",
    "render_tokens_json", "render_design_md", "render_preview_html",
]


def _theme_pairs(c: ThemeColors) -> list[tuple[str, str]]:
    return [(kebab(r), getattr(c, r)) for r in COLOR_ROLES]


def _common_ctx(ds: DesignSystem) -> dict[str, object]:
    ty = ds.typography
    return dict(
        ds=ds,
        colors={"light": _theme_pairs(ds.light), "dark": _theme_pairs(ds.dark)},
        sizes=[(k, num(v)) for k, v in sorted_sizes(ds)],
        weights=sorted(ty.weights.items(), key=lambda kv: (kv[1], kv[0])),
        line_heights=[(k, num(v)) for k, v in sorted(ty.line_heights.items(), key=lambda kv: (kv[1], kv[0]))],
        letter_spacing=[(k, num(v)) for k, v in sorted(ty.letter_spacing.items(), key=lambda kv: (kv[1], kv[0]))],
        radius=[(k, num(v)) for k, v in sorted(ds.radius.items(), key=lambda kv: (kv[1], kv[0]))],
        spacing=[(k, num(v)) for k, v in sorted_spacing(ds)],
        breakpoints=[(k, num(v)) for k, v in sorted(ds.layout.breakpoints.items(), key=lambda kv: (kv[1], kv[0]))],
        duration=num(ds.motion.duration_ms),
        container=num(ds.layout.container_max_width),
    )


def render_variables_css(ds: DesignSystem) -> str:
    return render("variables.css.j2", **_common_ctx(ds))


def render_tailwind_config(ds: DesignSystem) -> str:
    return render("tailwind.config.js.j2", **_common_ctx(ds))


def render_tailwind_v4(ds: DesignSystem) -> str:
    return render("tailwind-v4.css.j2", **_common_ctx(ds))


def _shadcn_map(c: ThemeColors) -> list[tuple[str, str]]:
    m = [
        ("background", c.background), ("foreground", c.text_primary),
        ("card", c.surface), ("card-foreground", c.text_primary),
        ("popover", c.surface), ("popover-foreground", c.text_primary),
        ("primary", c.accent), ("primary-foreground", c.accent_foreground),
        ("secondary", c.secondary), ("secondary-foreground", c.secondary_foreground),
        ("muted", c.secondary), ("muted-foreground", c.text_muted),
        ("accent", c.secondary), ("accent-foreground", c.secondary_foreground),
        ("destructive", c.destructive), ("destructive-foreground", c.destructive_foreground),
        ("border", c.border), ("input", c.border), ("ring", c.ring),
    ]
    return [(k, oklch_of(v)) for k, v in m]


def render_shadcn_theme(ds: DesignSystem) -> str:
    radius = f"{num(ds.radius.get('default', ds.radius.get('md', 8)) / 16)}rem"
    return render("shadcn-theme.css.j2", light=_shadcn_map(ds.light), dark=_shadcn_map(ds.dark), radius=radius)


_PAIRS = {
    "background": "text_primary", "surface": "text_primary", "text_primary": "background",
    "text_muted": "background", "accent": "background", "accent_foreground": "accent",
    "border": "background", "secondary": "secondary_foreground", "secondary_foreground": "secondary",
    "destructive": "background", "destructive_foreground": "destructive", "ring": "background",
}


def render_preview_html(ds: DesignSystem) -> str:
    ty = ds.typography
    cb, ci, cc = ds.components.button, ds.components.input, ds.components.card
    palette = []
    for r in COLOR_ROLES:
        other = _PAIRS[r]
        palette.append(dict(
            role=kebab(r), light=getattr(ds.light, r), dark=getattr(ds.dark, r),
            against=kebab(other),
            ratio_light=f"{ratio(getattr(ds.light, r), getattr(ds.light, other)):.2f}",
            ratio_dark=f"{ratio(getattr(ds.dark, r), getattr(ds.dark, other)):.2f}",
        ))
    sizes_map = {k: num(v) for k, v in ty.sizes.items()}
    heading_keys = [("h1", "4xl"), ("h2", "3xl"), ("h3", "2xl"), ("h4", "xl"), ("h5", "lg"), ("body", "base"), ("small", "sm")]
    type_rows = []
    for name, key in heading_keys:
        if key in ty.sizes:
            heading = name.startswith("h")
            type_rows.append(dict(
                name=name, size=num(ty.sizes[key]),
                family=css_safe((ty.display if heading else ty.sans).stack).replace('"', "'"),
                weight=ty.weights.get("bold" if heading else "normal", 400),
            ))
    gradient = css_safe(ds.gradients[0]) if ds.gradients else ""
    variants = [
        dict(label="Primary", cls="btn-primary"),
        dict(label="Secondary", cls="btn-secondary"),
        dict(label="Outline", cls=""),
        dict(label="Destructive", cls="btn-destructive"),
    ]
    stats = [
        dict(label="Metric one", value="1,284", note="+12% placeholder"),
        dict(label="Metric two", value="86%", note="Placeholder"),
        dict(label="Metric three", value="342", note="Placeholder"),
    ]
    hover_t = readable_transform(cb.hover.transform) if (cb.hover and cb.hover.transform) else None
    ctx = _common_ctx(ds)
    ctx.update(
        palette=palette,
        type_rows=type_rows,
        sizes_map=sizes_map,
        stats=stats,
        button_variants=variants,
        font_imports=list(ty.font_imports),
        sans=css_safe(ty.sans.stack),
        mono=css_safe(ty.mono.stack),
        display=css_safe(ty.display.stack),
        easing=css_safe(ds.motion.easing),
        base_size=num(ty.base_size_px),
        gap=num(ds.spacing.get("6", 64)),
        hero_pad=num(ds.spacing.get("6", 64)),
        btn_radius=num(cb.radius_px), input_radius=num(ci.radius_px), card_radius=num(cc.radius_px),
        btn_border=num(cb.border_width_px), input_border=num(ci.border_width_px), card_border=num(cc.border_width_px),
        btn_pad_y=num(cb.padding[0]), btn_pad_x=num(cb.padding[1]),
        input_pad_y=num(ci.padding[0]), input_pad_x=num(ci.padding[1]),
        card_pad=num(cc.padding[0]),
        btn_shadow=cb.shadow != "none", card_shadow=cc.shadow != "none",
        hover_transform=css_safe(hover_t) if hover_t else "",
        gradient=gradient,
    )
    return render("preview.html.j2", **ctx)


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def generate_all(ds: DesignSystem, out_dir: Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    renderers = {
        "variables.css": render_variables_css,
        "tailwind.config.js": render_tailwind_config,
        "tailwind-v4.css": render_tailwind_v4,
        "shadcn-theme.css": render_shadcn_theme,
        "tokens.json": render_tokens_json,
        "DESIGN.md": render_design_md,
        "preview.html": render_preview_html,
    }
    paths: list[Path] = []
    for name in OUTPUT_FILES:
        p = out / name
        _write(p, renderers[name](ds))
        paths.append(p)
    return paths


def write_blend_report(report: BlendReport, out_dir: Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / "blend-report.json"
    _write(p, report.model_dump_json(indent=2) + "\n")
    return p
