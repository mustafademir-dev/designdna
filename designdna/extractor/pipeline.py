"""Ham yakalamadan (RawCapture) işlenmiş SiteExtraction üretir."""

from __future__ import annotations

from designdna.extractor.color_miner import mine_colors
from designdna.extractor.component_miner import mine_components
from designdna.extractor.layout_miner import mine_layout, mine_spacing
from designdna.extractor.token_miner import mine_tokens
from designdna.extractor.typography_miner import mine_typography
from designdna.models import CounterTheme, RawCapture, SiteExtraction


def build_site_extraction(capture: RawCapture) -> SiteExtraction:
    """Miner'ları çalıştırıp tek bir SiteExtraction üretir (mobile yalnızca layout için)."""
    desktop = capture.desktop
    tokens = mine_tokens(desktop)
    colors = mine_colors(desktop, tokens)
    counter = None
    if capture.counter is not None:
        counter_tokens = mine_tokens(capture.counter)
        counter = CounterTheme(
            mode=capture.counter.natural_mode,
            colors=mine_colors(capture.counter, counter_tokens).roles,
        )
    return SiteExtraction(
        source=capture.source,
        natural_mode=desktop.natural_mode,
        colors=colors,
        typography=mine_typography(desktop),
        spacing=mine_spacing(desktop),
        layout=mine_layout(desktop, capture.mobile),
        components=mine_components(desktop, capture.hovers),
        tokens=tokens,
        counter=counter,
    )
