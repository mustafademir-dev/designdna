"""Gerçek ``locator.hover()`` ile hover durumu ölçümü (CONTRACTS §3.2)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from designdna.models import HOVER_PROPERTIES, ComponentType, ElementRecord, HoverDiff, RawSnapshot
from designdna.utils.color_math import composite, delta_e_ok, parse_color

if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import Page

PROBE_STYLE_ATTR = "data-designdna-probe"
_NO_MOTION_CSS = "*, *::before, *::after { transition: none !important; animation: none !important; }"
_BUTTON_INPUT_TYPES = {"button", "submit", "reset"}
_TEXT_INPUT_TYPES = {"text", "email", "search", "password", "url", "tel", "number"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_EXCLUDED_CARD_TAGS = {"html", "body", "header", "nav", "footer"}
_TYPE_ORDER: tuple[ComponentType, ...] = ("button", "input", "card")

_READ_JS = """
(i) => {
  const el = document.querySelector('[data-designdna-idx="' + i + '"]');
  if (!el) return null;
  const cs = getComputedStyle(el);
  return {
    'transform': cs.getPropertyValue('transform'),
    'background-color': cs.getPropertyValue('background-color'),
    'border-color': cs.getPropertyValue('border-top-color'),
    'box-shadow': cs.getPropertyValue('box-shadow'),
  };
}
"""

_PREPARE_JS = """
(i) => {
  const el = document.querySelector('[data-designdna-idx="' + i + '"]');
  if (!el) return null;
  el.scrollIntoView({block: 'center', inline: 'nearest'});
  const cs = getComputedStyle(el);
  return {
    duration: cs.getPropertyValue('transition-duration'),
    easing: cs.getPropertyValue('transition-timing-function'),
  };
}
"""

_ADD_STYLE_JS = """
([attr, css]) => {
  const s = document.createElement('style');
  s.setAttribute(attr, '1');
  s.textContent = css;
  document.head.appendChild(s);
  return true;
}
"""

_REMOVE_STYLE_JS = """
(attr) => {
  for (const s of document.querySelectorAll('style[' + attr + ']')) s.remove();
  return true;
}
"""


def _split_top(value: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    cur = ""
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def parse_duration_ms(value: str) -> float:
    """İlk transition-duration değerini ms'ye çevirir ('0.15s, 1s' -> 150.0)."""
    parts = _split_top(value or "")
    if not parts:
        return 0.0
    m = re.fullmatch(r"(-?[\d.]+)\s*(ms|s)?", parts[0])
    if not m:
        return 0.0
    number = float(m.group(1))
    return round(number if m.group(2) == "ms" else number * 1000.0, 2)


def parse_easing(value: str) -> str:
    parts = _split_top(value or "")
    return parts[0] if parts else "ease"


def _alpha_visible(value: str) -> bool:
    rgba = parse_color(value or "")
    return rgba is not None and rgba[3] > 0


def _effective_bg(by_idx: dict[int, ElementRecord], idx: int | None) -> tuple[float, float, float]:
    chain: list[ElementRecord] = []
    cur = by_idx.get(idx) if idx is not None else None
    while cur is not None:
        chain.append(cur)
        cur = by_idx.get(cur.parent_idx) if cur.parent_idx is not None else None
    rgb = (1.0, 1.0, 1.0)
    for el in reversed(chain):
        rgba = parse_color(el.styles.get("background-color", ""))
        if rgba is not None and rgba[3] > 0:
            rgb = composite(rgba, rgb)
    return rgb


def _is_button(el: ElementRecord) -> bool:
    if el.tag == "button" or el.role == "button":
        return True
    if el.tag == "input" and (el.input_type or "") in _BUTTON_INPUT_TYPES:
        return True
    if el.tag == "a":
        return any("btn" in c.lower() or "button" in c.lower() for c in el.classes)
    return False


def _is_input(el: ElementRecord) -> bool:
    if el.tag == "input":
        return (el.input_type or "text") in _TEXT_INPUT_TYPES
    return el.tag in ("textarea", "select")


def _has_border(el: ElementRecord) -> bool:
    for side in ("top", "right", "bottom", "left"):
        width = el.styles.get(f"border-{side}-width", "0px")
        style = el.styles.get(f"border-{side}-style", "none")
        try:
            w = float(width.replace("px", "") or 0)
        except ValueError:
            w = 0.0
        if w >= 1 and style not in ("none", "hidden") and _alpha_visible(el.styles.get(f"border-{side}-color", "")):
            return True
    return False


def classify_for_hover(el: ElementRecord, by_idx: dict[int, ElementRecord], text_ancestors: set[int], page_width: int) -> ComponentType | None:
    """CONTRACTS §3.6 kurallarının hover örneklemesi için yerel uygulaması."""
    if _is_button(el):
        return "button"
    if _is_input(el):
        return "input"
    if el.tag in _EXCLUDED_CARD_TAGS or el.area < 4000:
        return None
    if el.bbox.width >= 0.95 * page_width:
        return None  # tam genişlik sayfa/bölüm sarmalayıcıları kart değildir
    if el.idx not in text_ancestors:
        return None
    visible_bg = False
    rgba = parse_color(el.styles.get("background-color", ""))
    if rgba is not None and rgba[3] > 0:
        own = composite(rgba, _effective_bg(by_idx, el.parent_idx))
        visible_bg = delta_e_ok(own, _effective_bg(by_idx, el.parent_idx)) >= 0.02
    shadow = el.styles.get("box-shadow", "none")
    if visible_bg or _has_border(el) or (shadow and shadow != "none"):
        return "card"
    return None


def _selector(el: ElementRecord) -> str:
    s = el.tag
    if el.id:
        s += "#" + el.id
    for c in el.classes[:2]:
        s += "." + c
    return s


def _select_samples(snapshot: RawSnapshot, max_per_type: int) -> list[tuple[ComponentType, ElementRecord]]:
    by_idx = {e.idx: e for e in snapshot.elements}
    text_ancestors: set[int] = set()
    for el in reversed(snapshot.elements):
        if el.text_length > 0 or el.tag in _HEADINGS or el.idx in text_ancestors:
            parent = el.parent_idx
            if parent is not None:
                text_ancestors.add(parent)
    groups: dict[ComponentType, list[ElementRecord]] = {t: [] for t in _TYPE_ORDER}
    for el in snapshot.elements:
        kind = classify_for_hover(el, by_idx, text_ancestors, snapshot.viewport.width)
        if kind is not None:
            groups[kind].append(el)
    out: list[tuple[ComponentType, ElementRecord]] = []
    for kind in _TYPE_ORDER:
        ranked = sorted(groups[kind], key=lambda e: (-e.area, e.idx))[:max_per_type]
        out.extend((kind, e) for e in sorted(ranked, key=lambda e: e.idx))
    return out


def probe_hovers(page: "Page", snapshot: RawSnapshot, max_per_type: int = 5) -> list[HoverDiff]:
    """Seçilen buton/input/kart örnekleri üzerinde hover farkını ölçer."""
    from playwright.sync_api import Error as PlaywrightError

    results: list[HoverDiff] = []
    for kind, el in _select_samples(snapshot, max_per_type):
        style_added = False
        try:
            motion = page.evaluate(_PREPARE_JS, el.idx)
            if motion is None:
                continue
            page.evaluate(_ADD_STYLE_JS, [PROBE_STYLE_ATTR, _NO_MOTION_CSS])
            style_added = True
            page.mouse.move(0, 0)
            before = page.evaluate(_READ_JS, el.idx)
            page.locator(f'[data-designdna-idx="{el.idx}"]').first.hover(timeout=2000)
            after = page.evaluate(_READ_JS, el.idx)
            if before is None or after is None:
                continue
            changed = [p for p in HOVER_PROPERTIES if before[p] != after[p]]
            results.append(
                HoverDiff(
                    component_type=kind,
                    element_idx=el.idx,
                    selector=_selector(el),
                    before={p: before[p] for p in HOVER_PROPERTIES},
                    after={p: after[p] for p in HOVER_PROPERTIES},
                    changed=changed,
                    transition_duration_ms=parse_duration_ms(motion["duration"]),
                    transition_easing=parse_easing(motion["easing"]),
                )
            )
        except PlaywrightError:
            continue
        finally:
            try:
                if style_added:
                    page.evaluate(_REMOVE_STYLE_JS, PROBE_STYLE_ATTR)
                page.mouse.move(0, 0)
            except PlaywrightError:
                pass
    return results
