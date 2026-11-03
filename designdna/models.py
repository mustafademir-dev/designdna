"""DesignDNA veri sözleşmeleri (Pydantic v2).

Bu dosyayı YALNIZCA orkestratör değiştirir. Alanların anlamı ve üreten/tüketen
modüller CONTRACTS.md içinde açıklanmıştır.

Genel kurallar:
- Tüm renkler (aksi belirtilmedikçe) opak, küçük harfli `#rrggbb` hex'tir.
- Tüm uzunluklar CSS pikseli (float) cinsindendir.
- Modellerde zaman damgası yoktur; aynı girdi birebir aynı JSON'u üretmelidir.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HEX_PATTERN = r"^#[0-9a-f]{6}$"

ColorScheme = Literal["light", "dark"]
ThemeMode = Literal["light", "dark"]
ViewportName = Literal["desktop", "mobile"]
ComponentType = Literal["button", "input", "card"]
TokenKind = Literal["color", "dimension", "font", "radius", "shadow"]
ShadowStyle = Literal["none", "hard", "soft", "layered"]

#: Bilinen standart viewport'lar.
DESKTOP_VIEWPORT = (1440, 900)
MOBILE_VIEWPORT = (375, 812)

#: Blender'ın radius ve (≤24px) spacing için kuantize ettiği standart değerler.
STANDARD_RADII: tuple[float, ...] = (0, 2, 4, 6, 8, 12, 16, 24, 9999)

#: dom_scanner'ın her element için okuduğu computed style özellikleri (bu sırayla).
STYLE_PROPERTIES: tuple[str, ...] = (
    "color",
    "background-color",
    "background-image",
    "border-top-width",
    "border-right-width",
    "border-bottom-width",
    "border-left-width",
    "border-top-style",
    "border-right-style",
    "border-bottom-style",
    "border-left-style",
    "border-top-color",
    "border-right-color",
    "border-bottom-color",
    "border-left-color",
    "border-top-left-radius",
    "border-top-right-radius",
    "border-bottom-right-radius",
    "border-bottom-left-radius",
    "box-shadow",
    "backdrop-filter",
    "font-family",
    "font-size",
    "font-weight",
    "line-height",
    "letter-spacing",
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
    "row-gap",
    "column-gap",
    "display",
    "position",
    "max-width",
    "grid-template-columns",
    "flex-direction",
    "justify-content",
    "align-items",
    "opacity",
    "transform",
    "transition-property",
    "transition-duration",
    "transition-timing-function",
)

#: hover_probe'un önce/sonra karşılaştırdığı özellikler.
HOVER_PROPERTIES: tuple[str, ...] = ("transform", "background-color", "border-color", "box-shadow")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Kaynak tanımı (CLI)
# ---------------------------------------------------------------------------


class SourceSpec(_Model):
    """`--source` argümanının çözümlenmiş hali."""

    raw: str = Field(description="Kullanıcının yazdığı ham değer")
    location: str = Field(
        description="Normalize konum: http(s) URL, file:// URI ya da .json dosyasının file:// URI'si"
    )
    weight: float | None = Field(default=None, description="Verilen ağırlık; verilmediyse None")
    is_local: bool = Field(description="Yerel dosya mı (file://)")


# ---------------------------------------------------------------------------
# Ham tarama (yalnızca dom_scanner / hover_probe üretir)
# ---------------------------------------------------------------------------


class Viewport(_Model):
    name: ViewportName
    width: int
    height: int


class BoundingBox(_Model):
    """Sayfa koordinatları (scroll=0 iken document'e göre)."""

    x: float
    y: float
    width: float
    height: float


class ElementRecord(_Model):
    """Görünürlük filtresinden geçmiş tek bir element. Metin içeriği KOPYALANMAZ."""

    idx: int = Field(description="Snapshot içinde DOM sırasına göre 0'dan artan benzersiz indeks")
    parent_idx: int | None = Field(
        description="Görünür en yakın atanın idx'i (yoksa None). Görünmez atalar atlanır."
    )
    depth: int = Field(description="DOM derinliği (html=0)")
    tag: str = Field(description="Küçük harfli etiket adı")
    id: str = ""
    classes: list[str] = Field(default_factory=list)
    role: str | None = None
    input_type: str | None = Field(default=None, description="input ise type (küçük harf)")
    href: bool = Field(default=False, description="a[href] mi")
    text_length: int = Field(
        default=0, description="Elementin doğrudan (kendi) metin düğümlerinin trim'li toplam uzunluğu"
    )
    bbox: BoundingBox
    area: float = Field(description="width * height")
    in_viewport: bool = Field(description="scroll=0 iken ilk viewport ile kesişiyor mu")
    styles: dict[str, str] = Field(
        description="STYLE_PROPERTIES anahtarlarıyla getComputedStyle değerleri (ham string)"
    )


class CustomProperty(_Model):
    name: str = Field(description="'--' ile başlayan değişken adı")
    value: str = Field(description="Trim'lenmiş ham değer")
    selector: str = Field(description="Kuralın seçicisi, örn. ':root', 'html', 'body', '[data-theme=\"dark\"]'")
    media: str | None = Field(default=None, description="@media içindeyse koşul metni")


class FontFace(_Model):
    family: str = Field(description="Tırnaksız font-family")
    src: list[str] = Field(default_factory=list, description="url(...) içindeki adresler")
    weight: str | None = None
    style: str | None = None


class MediaQuery(_Model):
    condition: str = Field(description="@media koşul metni")
    min_width: float | None = None
    max_width: float | None = None
    prefers_color_scheme: ColorScheme | None = None


class Gradient(_Model):
    kind: Literal["linear", "radial"]
    value: str = Field(description="Tam gradient ifadesi, örn. 'linear-gradient(90deg, rgb(...) 0%, ...)'")
    element_idx: int
    area: float
    colors: list[str] = Field(default_factory=list, description="Gradient içindeki ham renk ifadeleri")


class RawSnapshot(_Model):
    """Tek bir (url, viewport, color_scheme) taramasının ham sonucu."""

    schema_version: int = 1
    tool_version: str
    source: str = Field(description="Taranan normalize URL (http(s) veya file://)")
    viewport: Viewport
    color_scheme: ColorScheme = Field(description="Tarama sırasında emüle edilen prefers-color-scheme")
    natural_mode: ThemeMode = Field(description="Viewport'taki en büyük opak arka plana göre doğal mod")
    dominant_background: str = Field(pattern=HEX_PATTERN, description="Doğal mod tespitinde kullanılan renk")
    page_height: float
    elements: list[ElementRecord]
    custom_properties: list[CustomProperty] = Field(default_factory=list)
    font_faces: list[FontFace] = Field(default_factory=list)
    font_links: list[str] = Field(
        default_factory=list, description="fonts.googleapis.com / fonts.bunny.net vb. font stylesheet linkleri"
    )
    media_queries: list[MediaQuery] = Field(default_factory=list)
    gradients: list[Gradient] = Field(default_factory=list)
    has_color_scheme_query: bool = Field(
        default=False, description="Stil dosyalarında prefers-color-scheme sorgusu var mı"
    )
    removed_overlays: list[str] = Field(
        default_factory=list,
        description="Gizlenen cookie/consent/overlay elementlerinin kısa tanımı, örn. 'div#cookie-banner'",
    )


class HoverDiff(_Model):
    component_type: ComponentType
    element_idx: int | None = Field(default=None, description="Desktop snapshot'taki eşleşen element idx'i")
    selector: str = Field(description="Örneği tanımlayan kısa seçici, örn. 'button.btn-primary'")
    before: dict[str, str] = Field(description="HOVER_PROPERTIES -> hover öncesi computed değer")
    after: dict[str, str] = Field(description="HOVER_PROPERTIES -> hover sonrası (end-state) computed değer")
    changed: list[str] = Field(description="Değişen özellik adları (HOVER_PROPERTIES sırasıyla)")
    transition_duration_ms: float = Field(description="İlk transition-duration değeri, ms")
    transition_easing: str = Field(description="İlk transition-timing-function değeri")


class RawCapture(_Model):
    """Bir kaynağın tüm ham çıkarımı. blend'in tek ham girdisi; .json olarak da verilebilir."""

    schema_version: int = 1
    tool_version: str
    source: str
    desktop: RawSnapshot = Field(description="Desktop 1440x900, color_scheme='light'")
    mobile: RawSnapshot | None = Field(
        default=None, description="Mobile 375x812; YALNIZCA layout/breakpoint için kullanılır"
    )
    counter: RawSnapshot | None = Field(
        default=None,
        description="Karşı şema desktop taraması; yalnızca natural_mode desktop'tan farklıysa doldurulur",
    )
    hovers: list[HoverDiff] = Field(default_factory=list)


class CacheEntry(_Model):
    """`.designdna/cache/<key>.json` dosyasının içeriği."""

    key: str
    source: str
    viewport: str = Field(description="'1440x900' biçiminde")
    color_scheme: ColorScheme
    tool_version: str
    snapshot: RawSnapshot
    hovers: list[HoverDiff] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# İşlenmiş çıkarım (miner'lar üretir, pipeline birleştirir)
# ---------------------------------------------------------------------------


class ColorToken(_Model):
    hex: str = Field(pattern=HEX_PATTERN, description="Alpha-composite sonrası görünen opak renk")
    oklch: tuple[float, float, float] = Field(description="(L 0..1, C, H derece 0..360)")
    weight: float = Field(default=0.0, description="Bu rolde toplam ağırlık payı (0..1)")
    raw: str | None = Field(default=None, description="Kaynaktaki ham ifade, örn. 'rgba(255,255,255,0.08)'")


class ColorRoles(_Model):
    """Bir temanın renk rolleri. Tüm roller zorunludur (bkz. CONTRACTS.md geri dönüş kuralları)."""

    background: ColorToken
    surface: ColorToken
    text_primary: ColorToken
    text_muted: ColorToken
    accent: ColorToken
    border: ColorToken


class ColorCluster(_Model):
    hex: str = Field(pattern=HEX_PATTERN)
    oklch: tuple[float, float, float]
    weight: float = Field(description="Toplam piksel-alanı ağırlığına göre normalize pay (0..1)")
    count: int = Field(description="Kümeye düşen kullanım sayısı")
    roles: list[str] = Field(default_factory=list, description="Bu kümenin aday olduğu roller")


class GradientToken(_Model):
    kind: Literal["linear", "radial"]
    value: str
    weight: float


class ColorAnalysis(_Model):
    roles: ColorRoles
    palette: list[ColorCluster] = Field(description="Ağırlığa göre azalan, eşitlikte hex artan")
    gradients: list[GradientToken] = Field(default_factory=list)


class TokenVar(_Model):
    name: str
    value: str
    kind: TokenKind
    selector: str
    media: str | None = None


class TypeStyle(_Model):
    font_family: str = Field(description="Fallback zincirindeki ana (ilk) font, tırnaksız")
    font_size_px: float
    line_height: float = Field(description="Birimsiz oran (line-height px / font-size); 'normal' -> 1.2")
    letter_spacing_em: float = Field(description="em cinsinden; 'normal' -> 0")
    font_weight: int
    samples: int = Field(description="Bu değerlerin geldiği örnek sayısı")


class FontUsage(_Model):
    family: str
    stack: str = Field(description="Ham font-family zinciri (en sık görülen)")
    weight: float = Field(description="Metin alanına göre kullanım payı (0..1)")
    is_monospace: bool


class Typography(_Model):
    body_family: str
    body_stack: str
    display_family: str = Field(description="Başlıklarda (h1-h3) en sık font; yoksa body_family")
    display_stack: str
    mono_family: str | None = Field(default=None, description="code/pre/kbd'de görülen monospace font")
    mono_stack: str | None = None
    families: list[FontUsage] = Field(default_factory=list)
    styles: dict[str, TypeStyle] = Field(
        description="Anahtarlar: h1..h6, p, small, code, button (yalnız sayfada olanlar)"
    )
    base_size_px: float = Field(description="Gövde (p) font boyutu; yoksa 16")
    measured_ratio: float = Field(description="Başlık/gövde boyutlarının medyan geometrik oranı")
    scale_ratio: float = Field(description="En yakın standart oran: 1.125,1.2,1.25,1.333,1.414,1.5,1.618")
    font_faces: list[FontFace] = Field(default_factory=list)
    font_links: list[str] = Field(default_factory=list)


class Spacing(_Model):
    base: Literal[4, 8]
    scale: list[float] = Field(description="Artan, tekrarsız standart spacing adımları (px)")
    observed: list[float] = Field(description="Aykırılar atıldıktan sonra görülen tekrarsız değerler (artan)")


class Layout(_Model):
    container_max_width: float | None = None
    grid_columns: list[int] = Field(default_factory=list, description="Görülen kolon sayıları, sıklığa göre")
    flex_alignments: list[str] = Field(
        default_factory=list, description="'justify-content/align-items' çiftleri, sıklığa göre, örn. 'space-between/center'"
    )
    breakpoints: list[float] = Field(default_factory=list, description="Artan, tekrarsız px")


class HoverStyle(_Model):
    samples: int
    transform: str | None = Field(default=None, description="En sık hover transform'u ('none' değilse)")
    background_changes: bool = False
    border_changes: bool = False
    shadow_changes: bool = False
    duration_ms: float = 0.0
    easing: str = "ease"


class ComponentStats(_Model):
    """DESIGN.md Do's & Don'ts kanıtları için ham oranlar."""

    count: int
    with_border: float = Field(description="Kenarlığı olan örneklerin oranı (0..1)")
    with_shadow: float
    with_backdrop: float
    with_background: float
    radius_values: dict[str, int] = Field(
        default_factory=dict, description="'8' -> adet (px değeri string anahtar)"
    )


class ComponentStyle(_Model):
    border_radius_px: float = Field(description="En sık (ağırlıklı) radius; % ise px'e çevrilmiş")
    border_width_px: float
    border_style: str = "none"
    border_color: str | None = Field(default=None, pattern=HEX_PATTERN)
    box_shadow: str = Field(description="En sık box-shadow ham değeri, yoksa 'none'")
    backdrop_filter: str = Field(default="none")
    padding: tuple[float, float, float, float] = Field(description="top, right, bottom, left px")
    background: str | None = Field(default=None, pattern=HEX_PATTERN)
    foreground: str | None = Field(default=None, pattern=HEX_PATTERN)
    stats: ComponentStats
    hover: HoverStyle | None = None


class Components(_Model):
    button: ComponentStyle | None = None
    input: ComponentStyle | None = None
    card: ComponentStyle | None = None
    shadow_style: ShadowStyle = Field(description="Sitenin genel gölge karakteri")
    shadows: list[str] = Field(default_factory=list, description="Görülen box-shadow değerleri, sıklığa göre")


class CounterTheme(_Model):
    mode: ThemeMode
    colors: ColorRoles


class SiteExtraction(_Model):
    source: str
    natural_mode: ThemeMode
    colors: ColorAnalysis
    typography: Typography
    spacing: Spacing
    layout: Layout
    components: Components
    tokens: list[TokenVar] = Field(default_factory=list)
    counter: CounterTheme | None = Field(default=None, description="Taramada gerçek karşı tema yakalandıysa")


# ---------------------------------------------------------------------------
# Harmanlanmış sistem (blender üretir, generator'ların TEK girdisi)
# ---------------------------------------------------------------------------


class ThemeColors(_Model):
    background: str = Field(pattern=HEX_PATTERN)
    surface: str = Field(pattern=HEX_PATTERN)
    text_primary: str = Field(pattern=HEX_PATTERN)
    text_muted: str = Field(pattern=HEX_PATTERN)
    accent: str = Field(pattern=HEX_PATTERN)
    accent_foreground: str = Field(pattern=HEX_PATTERN)
    border: str = Field(pattern=HEX_PATTERN)
    secondary: str = Field(pattern=HEX_PATTERN, description="surface'ten türetilmiş ikincil zemin")
    secondary_foreground: str = Field(pattern=HEX_PATTERN)
    destructive: str = Field(pattern=HEX_PATTERN)
    destructive_foreground: str = Field(pattern=HEX_PATTERN)
    ring: str = Field(pattern=HEX_PATTERN)


class FontSpec(_Model):
    family: str
    stack: str = Field(description="Kullanıma hazır CSS font-family zinciri")
    source: str = Field(description="Bu fontun geldiği kaynak (SourceRef.source)")


class TypographySystem(_Model):
    sans: FontSpec = Field(description="Gövde fontu")
    mono: FontSpec
    display: FontSpec = Field(description="Başlık fontu")
    base_size_px: float
    scale_ratio: float
    sizes: dict[str, float] = Field(description="xs, sm, base, lg, xl, 2xl, 3xl, 4xl, 5xl -> px")
    line_heights: dict[str, float] = Field(description="tight, normal, relaxed -> oran")
    weights: dict[str, int] = Field(description="normal, medium, semibold, bold")
    letter_spacing: dict[str, float] = Field(description="tight, normal, wide -> em")
    font_imports: list[str] = Field(default_factory=list, description="Google Fonts vb. stylesheet URL'leri")


class ShadowSystem(_Model):
    style: ShadowStyle
    sm: str
    md: str
    lg: str


class MotionSystem(_Model):
    duration_ms: float
    easing: str
    hover_transform: str | None = Field(
        default=None, description="Okunur biçimde, örn. 'translate(-2px, -2px)' (matrix() değil)"
    )
    hover_description: str = Field(description="İnsan-okur özet (Türkçe; CLI için), örn. 'translate(-2px,-2px) + gölge büyür'")
    measured: bool = Field(
        default=True, description="Süre/easing gerçekten ölçüldü mü; False ise varsayılan değerlerdir (DESIGN.md kural yazmaz)"
    )


class LayoutSystem(_Model):
    container_max_width: float
    breakpoints: dict[str, float] = Field(description="sm, md, lg, xl, 2xl -> px")
    grid_columns: int
    container_measured: bool = Field(default=True, description="False ise container_max_width varsayılandır")
    grid_measured: bool = Field(default=True, description="False ise grid_columns varsayılandır")


class ComponentSpec(_Model):
    radius_px: float = Field(description="STANDARD_RADII'den bir değer")
    border_width_px: float
    border_style: str
    shadow: str = Field(description="CSS box-shadow veya 'none'")
    padding: tuple[float, float, float, float]
    backdrop_filter: str = "none"
    hover: HoverStyle | None = None
    stats: ComponentStats | None = None
    source: str = Field(description="Bu bileşen karakterinin geldiği kaynak")


class ComponentSystem(_Model):
    button: ComponentSpec
    input: ComponentSpec
    card: ComponentSpec


class SourceRef(_Model):
    source: str
    weight: float = Field(description="Normalize ağırlık (toplam 1.0)")
    natural_mode: ThemeMode
    roles: list[str] = Field(default_factory=list, description="Bu kaynaktan alınan roller")


class DesignSystem(_Model):
    schema_version: int = 1
    tool_version: str
    sources: list[SourceRef]
    base_mode: ThemeMode = Field(description="Baskın kaynağın doğal modu")
    light: ThemeColors
    dark: ThemeColors
    gradients: list[str] = Field(default_factory=list)
    typography: TypographySystem
    spacing: dict[str, float] = Field(description="'0','1','2',... -> px (artan)")
    spacing_base: Literal[4, 8]
    radius: dict[str, float] = Field(description="none, sm, md, lg, xl, full -> px; 'default' shadcn --radius")
    shadows: ShadowSystem
    motion: MotionSystem
    layout: LayoutSystem
    components: ComponentSystem


# ---------------------------------------------------------------------------
# Rapor
# ---------------------------------------------------------------------------


class SourceWeight(_Model):
    source: str
    input_weight: float | None
    normalized_weight: float
    eligible: bool = Field(description="Ağırlık >= 0.2 ise True (rol alabilir)")


class RoleAssignment(_Model):
    role: str = Field(description="CONTRACTS.md'deki rol adlarından biri")
    source: str
    reason: str


class ContrastFix(_Model):
    theme: ThemeMode
    role: str
    against: str = Field(description="Karşılaştırılan rol(ler), örn. 'background,surface'")
    original: str = Field(pattern=HEX_PATTERN)
    adjusted: str = Field(pattern=HEX_PATTERN)
    ratio_before: float
    ratio_after: float
    target: float
    achieved: bool


class BlendReport(_Model):
    schema_version: int = 1
    tool_version: str
    sources: list[SourceWeight]
    roles: list[RoleAssignment]
    contrast_fixes: list[ContrastFix] = Field(default_factory=list)
    counter_theme: Literal["captured", "derived"]
    warnings: list[str] = Field(default_factory=list)
