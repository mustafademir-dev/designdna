# CONTRACTS.md — Modül Sözleşmeleri

Bu dosya ve `designdna/models.py` **yalnızca orkestratör** tarafından değiştirilir.
Sözleşme değişikliği gerekiyorsa raporunda "SÖZLEŞME TALEBİ" başlığıyla iste; kendin değiştirme.

## 0. Genel kurallar

- Python ≥ 3.10, `from __future__ import annotations`. Dosya yolları `pathlib.Path`, dosya I/O `encoding="utf-8"`.
- Windows + Linux uyumlu. Sabit `/` ayırıcılı string yol birleştirme yok.
- **Determinizm:** rastgelelik, zaman damgası, `set` iterasyon sırasına bağımlılık yok. Sıralamalarda eşitlik hep ikinci bir anahtarla (çoğunlukla hex/isim) çözülür. JSON yazarken `model_dump_json(indent=2)` veya `json.dumps(..., indent=2, ensure_ascii=False, sort_keys=False)`.
- Kodda placeholder yok (`TODO`, gövdesi yalnızca `pass`/`...` olan fonksiyon). Yapılamayanlar `TODO.md`'ye.
- Hatalar: kullanıcıya gidecek hatalar `designdna.errors.DesignDNAError` (veya alt sınıfı) ile, **Türkçe** mesajla.
- Tarayıcıya **yalnızca** `designdna/extractor/dom_scanner.py` ve `designdna/extractor/hover_probe.py` dokunur (+ e2e testleri). Chromium daima `designdna.utils.browser.launch_chromium(playwright)` ile başlatılır.
- Tarayıcı gerektiren testler `@pytest.mark.browser` ile işaretlenir; conftest Chromium yoksa bunları otomatik skip eder. Bu ortamda Chromium **var** (`/opt/pw-browsers/chromium`), yani browser testleri gerçekten koşar.
- Metin içeriği, görsel, svg, logo kopyalanmaz. Snapshot'ta yalnızca `text_length` tutulur.
- Test komutu: `.venv/bin/python -m pytest <dosya> -q` (proje kökünden). Paket editable kurulu.

## 1. Dosya haritası ve sahiplik

| Dosya | Sahip (faz) |
|---|---|
| `pyproject.toml`, `designdna/models.py`, `designdna/errors.py`, `designdna/utils/browser.py`, `designdna/__init__.py`, `tests/conftest.py`, `CONTRACTS.md`, `PROGRESS.md` | orkestratör (0) |
| `designdna/utils/color_math.py`, `tests/test_color_math.py` | builder (1) |
| `tests/fixtures/*.html`, `tests/expected/*.json`, `tests/fixtures/sample_snapshot.json`, `tests/fixtures/sample_design_system.json` | fixture-author (1) |
| `designdna/extractor/dom_scanner.py`, `designdna/extractor/js/scan.js`, `designdna/extractor/hover_probe.py`, `designdna/cache.py`, `scripts/regen_fixture_snapshots.py`, `tests/fixtures/snapshots/*.capture.json`, `tests/test_dom_scanner.py`, `tests/test_hover_probe.py`, `tests/test_cache.py` | builder 2a |
| `designdna/extractor/color_miner.py`, `designdna/extractor/typography_miner.py`, `tests/test_color_miner.py`, `tests/test_typography_miner.py` | builder 2b |
| `designdna/extractor/token_miner.py`, `designdna/extractor/layout_miner.py`, `designdna/extractor/component_miner.py`, `tests/test_token_miner.py`, `tests/test_layout_miner.py`, `tests/test_component_miner.py` | builder 2c |
| `designdna/extractor/pipeline.py`, `designdna/synthesizer/blender.py`, `tests/test_pipeline_fixtures.py`, `tests/test_blender.py`, `tests/test_contrast.py` | builder 3a |
| `designdna/generators/**`, `tests/test_generators.py`, `tests/test_preview_e2e.py` | builder 3b |
| `designdna/sources.py`, `designdna/cli.py`, `skill/SKILL.md`, `tests/test_sources.py`, `tests/test_cli.py`, `tests/test_determinism.py` | builder 3c |

## 2. `designdna/utils/color_math.py` (saf, harici bağımlılık yok)

```python
RGB = tuple[float, float, float]          # 0..1 sRGB (gamma'lı)
RGBA = tuple[float, float, float, float]  # alpha 0..1

def parse_color(value: str) -> RGBA | None
    # hex (#rgb, #rgba, #rrggbb, #rrggbbaa), rgb()/rgba() (virgüllü ve boşluklu/slash sözdizimi, % dahil),
    # hsl()/hsla(), oklch(L C H [/ a]) (L % veya 0..1), 'transparent' -> (0,0,0,0),
    # temel isimli renkler (en az: black, white, red, green, blue, gray/grey, yellow, orange, purple, pink, transparent).
    # Çözülemezse None. 'currentcolor', 'inherit', var(...) -> None.
def srgb_to_linear(c: float) -> float ; def linear_to_srgb(c: float) -> float
def rgb_to_oklab(rgb: RGB) -> tuple[float, float, float]
def oklab_to_rgb(lab) -> RGB                       # kırpmasız (gamut dışı olabilir)
def oklab_to_oklch(lab) -> tuple[float, float, float]   # H derece 0..360; C<1e-4 ise H=0
def oklch_to_oklab(lch) -> tuple[float, float, float]
def rgb_to_oklch(rgb: RGB) -> tuple[float, float, float]
def in_gamut(rgb: RGB, eps: float = 1e-6) -> bool
def gamut_map_oklch(lch) -> RGB
    # L ve H sabit, C ikili arama ile düşürülür (≥ 20 iterasyon) -> sRGB içinde; sonunda [0,1] clamp.
def oklch_to_rgb(lch) -> RGB                       # gamut_map_oklch kullanır
def rgb_to_hex(rgb: RGB) -> str                    # '#rrggbb' küçük harf, round(x*255)
def hex_to_rgb(hex_str: str) -> RGB
def composite(fg: RGBA, bg: RGB) -> RGB            # alpha-composite (sRGB uzayında, tarayıcı gibi)
def composite_over(colors: list[RGBA], base: RGB = (1,1,1)) -> RGB
    # colors: en alttan üste doğru katmanlar; base en altta opak zemin
def relative_luminance(rgb: RGB) -> float          # WCAG 2.x
def contrast_ratio(a: RGB, b: RGB) -> float        # (L1+0.05)/(L2+0.05), ≥1
def delta_e_ok(a: RGB, b: RGB) -> float            # OKLab öklid mesafesi
def normalize_hex(value: str, background: RGB = (1,1,1)) -> str | None
    # parse + yarı saydamsa background üzerine composite + hex; çözülemezse None
def oklch_css(rgb: RGB) -> str                     # 'oklch(0.628 0.258 29.23)' (L 3, C 3, H 2 ondalık)
def hsl_components(rgb: RGB) -> tuple[float, float, float]  # shadcn için (H derece, S %, L %)
```

## 3. Extractor

### 3.1 `dom_scanner.py` (tarayıcı)
```python
TOOL_VERSION = designdna.__version__
def scan_page(page, source: str, viewport: Viewport, color_scheme: ColorScheme) -> RawSnapshot
    # sayfa zaten açık ve yüklenmiş; scroll, overlay temizliği, tek page.evaluate(scan.js), Python tarafı doğal mod.
def load_page(page, url: str) -> None
    # goto(wait_until="domcontentloaded"), networkidle ≤3 sn (timeout yutulur), document.fonts.ready,
    # lazy-load scroll (hızlı adımlar, ≤10.000px), en üste dönüş.
def detect_natural_mode(elements: list[ElementRecord], viewport: Viewport) -> tuple[ThemeMode, str]
    # SAF fonksiyon: in_viewport elementler içinde opak (alpha==1) background-color'ı olan ve
    # viewport ile kesişim alanı en büyük olan elementin rengi; eşitlikte daha derin (depth büyük) olan.
    # Hiç yoksa '#ffffff'. OKLCH L < 0.5 -> 'dark', aksi 'light'.
def capture_source(url: str, *, browser=None) -> RawCapture
    # desktop (1440x900, color_scheme='light') + hover_probe; mobile (375x812, 'light');
    # desktop.has_color_scheme_query ise desktop 'dark' taraması -> natural_mode desktop'tan farklıysa counter, değilse None.
```
- JS (`js/scan.js`) tek `page.evaluate` ile: tüm elementleri gezer, görünürlük filtresi (display:none, visibility:hidden, opacity:0 (hesaplanmış, ataların opaklığı dahil değil), w<2 veya h<2 at), `STYLE_PROPERTIES`'i okur, `:root/html/body/[data-theme…]` seçicili kurallardaki `--*` değişkenleri (cross-origin `cssRules` hataları try/catch ile yutulur, `@media` içindeki kurallar `media` ile), `@font-face`, `@media` (min/max-width px; em/rem ise ×16), `prefers-color-scheme` varlığı, `background-image` gradient'leri, font linkleri.
- Overlay temizliği JS'te ve taramadan ÖNCE: id/class/aria-label/metninde (küçük harf) `cookie`, `consent`, `gdpr` geçen elementler veya `position: fixed` olup viewport alanının %30'undan fazlasını kaplayanlar `display:none !important` ile gizlenir; `header`, `nav`, `[role=banner]` ve bunları içeren/bunların içindeki elementler asla gizlenmez. Gizlenenler `removed_overlays`'e `tag#id.class` biçiminde yazılır.
- Kaynak URL normalize edilmiş olarak gelir (CLI `file://` URI'ye çevirir).

### 3.2 `hover_probe.py` (tarayıcı)
```python
def probe_hovers(page, snapshot: RawSnapshot, max_per_type: int = 5) -> list[HoverDiff]
```
- Buton/input/kart seçimi §3.6'daki sezgisel kurallarla (aynı mantık; ortak fonksiyon `component_miner.classify_element` saf olduğu için import edilebilir). Elementler `data-designdna-idx` özniteliğiyle eşlenebilir (scan.js bu özniteliği basar).
- Önce `scrollIntoView`, `transition-duration`/`timing-function` oku; sonra `*, *::before, *::after { transition: none !important; animation: none !important; }` enjekte et, `locator.hover()`, `HOVER_PROPERTIES` oku, stil etiketini kaldır, fareyi (0,0)'a taşı. `border-color` için `border-top-color` kullanılabilir.

### 3.3 `designdna/cache.py`
```python
DEFAULT_CACHE_DIR = Path(".designdna") / "cache"
def cache_key(url: str, viewport: str, color_scheme: str, tool_version: str = TOOL_VERSION) -> str
    # sha256((url + viewport + color_scheme + tool_version).encode('utf-8')).hexdigest()
class CacheStore:
    def __init__(self, root: Path | None = None)   # None -> Path.cwd()/DEFAULT_CACHE_DIR
    def path_for(self, key: str) -> Path
    def save_capture(self, capture: RawCapture) -> list[Path]
        # desktop(+hovers), mobile, counter ayrı CacheEntry dosyaları; key = cache_key(source, '1440x900'/'375x812', scheme)
    def load_capture(self, url: str) -> RawCapture | None
        # desktop yoksa None; mobile/counter varsa eklenir
    def has(self, url: str) -> bool
def load_capture_file(path: Path) -> RawCapture   # .json dosyasından (RawCapture JSON'u)
```

### 3.4 `token_miner.py`
```python
NOISE_PREFIXES = ("--tw-", "--wp-", "--wp--", "--bs-", "--chakra-", "--mantine-", "--rs-", "--swiper-", "--fa-", "--toastify-")
def is_noise(name: str) -> bool
def classify_token(name: str, value: str) -> TokenKind | None   # color | dimension (px/rem/em) | font | radius | shadow; çözülemezse None
def mine_tokens(snapshot: RawSnapshot) -> list[TokenVar]
    # yalnızca seçici :root, html, body veya [data-theme...] olanlar; gürültü atılır; var(--x) referansları
    # aynı snapshot içinden en fazla 5 seviye çözülür; çözülemeyen/geçersiz atılır.
    # radius: isimde 'radius'/'rounded' geçen boyut; shadow: isimde 'shadow' veya değer box-shadow biçimi.
    # Sıralama: selector sırası (:root, html, body, [data-theme...]), sonra isim.
```

### 3.5 `color_miner.py`
```python
CLUSTER_DELTA_E = 0.03
def cluster_colors(samples: list[tuple[str, float]]) -> list[ColorCluster]
    # samples: (hex, weight). Ağırlığa göre azalan, eşitlikte hex artan sırada açgözlü: her renk, mevcut
    # bir küme merkezine ΔE_OK < 0.03 ise o kümeye (merkez = ilk/en ağır renk) eklenir; değilse yeni küme.
def effective_background(snapshot: RawSnapshot, idx: int) -> RGB
    # elementin ve atalarının background-color'larını alttan üste composite eder (en altta beyaz).
def mine_colors(snapshot: RawSnapshot, tokens: list[TokenVar] | None = None) -> ColorAnalysis
```
Rol kuralları (ağırlık = piksel alanı; metin rollerinde alan × (text_length>0)):
- `background`: snapshot.dominant_background (doğal mod rengi).
- `surface`: background'dan farklı (ΔE ≥ 0.03) opak/composite arka planlardan, kart/panel adayı (§3.6 card) olanların ağırlıklı en sık rengi; yoksa background'a göre L'si ±0.03 kaydırılmış türetilmiş renk.
- `text-primary`: metinli elementlerin (text_length>0) `color`'ı, effective background üzerine composite, en ağır küme.
- `text-muted`: text-primary'den ΔE ≥ 0.05 farklı, background'a kontrastı daha düşük ikinci metin kümesi; yoksa text-primary'nin L'si background'a doğru 0.25 kaydırılmış hali.
- `accent`: buton (§3.6) arka planları, `a[href]` metin renkleri, badge/aktif öğeler içinde kromatik (C ≥ 0.05) en ağır küme; yoksa en kromatik buton arka planı; o da yoksa text-primary.
- `border`: `border-*-width ≥ 1` ve style ≠ none olan elementlerin border rengi, effective background üzerine composite, en ağır küme; yoksa background'un L'si ±0.1 kaydırılmış.
- Token önceliği: isimde `background|bg`, `surface|card|panel`, `foreground|text`, `muted`, `accent|primary|brand`, `border` geçen renk token'ları, değeri paletteki bir kümeye ΔE < 0.03 yakınsa o rol için tercih edilir.
- `palette`: tüm (bg, metin, border) renk örneklerinin kümelenmiş hali; `weight` toplamı 1.
- `gradients`: snapshot.gradients → GradientToken (weight = alan payı), tekrarlar birleşir.

### 3.6 `component_miner.py`
```python
def classify_element(el: ElementRecord, snapshot: RawSnapshot) -> ComponentType | None
    # button: tag=button, input[type=button|submit|reset], a ile class'ında 'btn'/'button' geçen, role=button
    # input: input[type in text,email,search,password,url,tel,number veya type yok], textarea, select
    # card: buton/input olmayan; görünür arka planı (parent'ın effective bg'sinden ΔE≥0.02 farklı) VEYA border VEYA box-shadow'u olan;
    #       alanı ≥ 4000px² ve en az bir torunu başlık (h1-h6) veya metinli (text_length>0) eleman olan kutu; html/body/header/nav/footer hariç.
def mine_components(snapshot: RawSnapshot, hovers: list[HoverDiff]) -> Components
    # her tip için ağırlıklı (alan) en sık radius/border/shadow/backdrop/padding; stats oranları; hovers ile HoverStyle.
    # shadow_style: tüm görünür gölgeler: yok -> 'none'; blur=0 olan baskın -> 'hard'; birden fazla katman (virgül) baskın -> 'layered'; aksi 'soft'.
```

### 3.7 `typography_miner.py`
```python
TYPE_SCALE_RATIOS = (1.125, 1.2, 1.25, 1.333, 1.414, 1.5, 1.618)
MONO_HINTS = ("mono", "code", "courier", "consolas", "menlo", "monaco")   # + generic 'monospace'
def primary_family(stack: str) -> str          # ilk aile, tırnaksız; 'monospace'/'sans-serif' generic ise o
def mine_typography(snapshot: RawSnapshot) -> Typography
```
- `styles` anahtarları: h1..h6, p, small, code, button (yalnız sayfada olanlar), her biri en sık (alan ağırlıklı) değerler.
- `measured_ratio`: mevcut h1..h6 boyutlarının p (base) boyutuna oranlarından adım başına geometrik oran: her başlık için `(size/base) ** (1/n)` (h6..h1 sırasıyla n = basamak sayısı, h4=1, h3=2, h2=3, h1=4; h5/h6 ≤ base ise atlanır) değerlerinin medyanı; hesaplanamazsa 1.25. `scale_ratio`: en yakın standart oran.
- body: p/li/span/div metinlerinin alan ağırlıklı en sık ana fontu; display: h1-h3; mono: code/pre/kbd/samp (monospace değilse None).

### 3.8 `layout_miner.py`
```python
def mine_spacing(snapshot: RawSnapshot) -> Spacing
    # padding/margin/gap (>0) değerleri; IQR dışı aykırılar atılır (Q3 + 1.5*IQR üstü); 4'ün katlarının
    # (8 olmayan) payı ≥ %25 ise base=4, değilse 8. scale: base'e göre standart ölçek (4: 4,8,12,16,24,32,48,64; 8: 8,16,24,32,48,64,96).
def mine_layout(desktop: RawSnapshot, mobile: RawSnapshot | None = None) -> Layout
    # container_max_width: max-width px olan ve genişliği ≥ 600 olan elementlerin en sık değeri.
    # grid_columns: display grid olanların grid-template-columns iz sayısı.
    # breakpoints: desktop+mobile media_queries min/max-width değerleri.
```

### 3.9 `pipeline.py`
```python
def build_site_extraction(capture: RawCapture) -> SiteExtraction
    # tokens = mine_tokens(desktop); colors = mine_colors(desktop, tokens); typography = mine_typography(desktop);
    # spacing = mine_spacing(desktop); layout = mine_layout(desktop, mobile); components = mine_components(desktop, hovers);
    # counter: capture.counter varsa CounterTheme(mode=counter.natural_mode, colors=mine_colors(counter).roles)
```
Mobile snapshot renk/token kaynağı OLMAZ.

## 4. `designdna/synthesizer/blender.py`
```python
ELIGIBILITY_THRESHOLD = 0.2
def normalize_weights(weights: list[float | None]) -> list[float]   # None'lar varsa hepsi eşit; toplam 1.0
def quantize_radius(px: float) -> float      # >40 -> 9999; aksi STANDARD_RADII[:-1]'deki en yakın (eşitlikte küçük)
def quantize_spacing(px: float) -> float     # ≤24: {0,2,4,6,8,12,16,24} en yakın; >24: {32,40,48,64,80,96,128} en yakın
def ensure_contrast(color: str, against: list[str], target: float) -> tuple[str, float, bool]
    # yalnızca OKLCH L ±0.02 adım (≤40 adım), H ve C korunur, her adımda gamut map; yön: against'ların
    # ortalama L'sinden uzaklaşan yön. Ulaşılamazsa beyaz/siyahtan hedefi sağlayanı (yoksa en yüksek oranı) seç; achieved=False ise uyarı.
def blend(extractions: list[SiteExtraction], weights: list[float | None] | None = None) -> tuple[DesignSystem, BlendReport]
```
**Rol adları** (BlendReport.roles ve SourceRef.roles): `background`, `surface`, `text-primary`, `text-muted`, `border`, `font-body`, `font-mono`, `spacing`, `layout`, `accent`, `radius-control`, `hover-style`, `shadow`, `font-display`, `radius-card`.
- Grup 1 → 1. kaynak: background, surface, text-primary, text-muted, border, font-body, font-mono, spacing, layout.
- Grup 2 → 2. kaynak (yoksa 1.): accent, radius-control (buton+input), hover-style.
- Grup 3 → 3. kaynak (yoksa 2., yoksa 1.): shadow, font-display, radius-card.
- Kaynak sırası: normalize ağırlık azalan, eşitlikte girdi sırası. Ağırlığı < 0.2 olan rol almaz; `warnings`'e Türkçe not.
- Kontrast kuralları: text-primary & text-muted vs {background, surface} ≥ 4.5; accent-foreground vs accent ≥ 4.5 (accent-foreground önce beyaz/siyahtan yüksek oranlı olan); border vs {background, surface} ≥ 3.0; secondary-foreground vs secondary ≥ 4.5; destructive-foreground vs destructive ≥ 4.5. Light ve dark ayrı ayrı. Her düzeltme `ContrastFix`.
- Karşı tema: baskın kaynakta `counter` varsa onun renkleri (yine kontrast kontrolünden geçer), `counter_theme='captured'`; yoksa türet (`'derived'`): dark için background L→0.12–0.16 bandına (clamp), surface L→0.18–0.22, metinler: L' = 1 - L (C korunur), C > 0.2 olan renklerde C×0.85; light için tersi (background L→0.97–0.99, surface L→0.93–0.96). Sonra kontrast kontrolleri.
- `destructive`: light `#dc2626`, dark `#ef4444` (kontrast kontrolünden geçer). `ring` = accent. `secondary` = surface'in L'si 0.04 (light: aşağı, dark: yukarı) kaydırılmış hali.
- radius dict: none=0, sm, md, lg, xl, full=9999, default=radius-control kaynağının buton radius'u; tamamı kuantize.
- spacing dict: kaynağın scale'i quantize edilerek `'0':0, '1':..` artan, tekrarsız.

## 5. Generators (`designdna/generators/`, Jinja2, girdi yalnızca `DesignSystem`)
```python
OUTPUT_FILES = ("variables.css", "tailwind.config.js", "tailwind-v4.css", "shadcn-theme.css", "tokens.json", "DESIGN.md", "preview.html")
def generate_all(ds: DesignSystem, out_dir: Path) -> list[Path]   # OUTPUT_FILES'ı yazar (out_dir yoksa oluşturur)
def write_blend_report(report: BlendReport, out_dir: Path) -> Path   # blend-report.json
def render_variables_css(ds) -> str ; render_tailwind_config(ds) -> str ; render_tailwind_v4(ds) -> str
def render_shadcn_theme(ds) -> str ; render_tokens_json(ds) -> str ; render_design_md(ds) -> str ; render_preview_html(ds) -> str
```
Şablonlar `designdna/generators/templates/*.j2` (paket verisi; `importlib.resources` ile yüklenir, `PackageLoader` kullanılabilir).

## 6. CLI (`designdna/sources.py`, `designdna/cli.py`)
```python
WEIGHT_RE = re.compile(r"@(\d+(?:\.\d+)?)$")
def parse_source(text: str) -> SourceSpec
    # son '@' sonrası WEIGHT_RE ile pozitif sayıysa ağırlık, değilse '@' konumun parçası.
    # '@' sonrası 0 ise de (pozitif değil) '@' konumun parçasıdır, ağırlık None (spec §6).
    # http(s):// ve file:// olduğu gibi; 'C:\\...' / 'C:/...' -> PureWindowsPath(...).as_uri();
    # diğer yerel yollar -> Path(...).expanduser().resolve().as_uri().
def source_to_path(spec: SourceSpec) -> Path | None   # file:// ise yerel Path
```
- `designdna extract --source ... [--refresh] [--cache-dir PATH]`
- `designdna blend --source ... --output DIR [--cache-dir PATH]`  (.json kaynak → `load_capture_file`; diğerleri cache; cache yoksa Türkçe hata, çıkış kodu ≠ 0; tarayıcı AÇMAZ)
- `designdna run --source ... --output DIR [--refresh] [--cache-dir PATH]`
- `designdna preview DIR` (`webbrowser.open(preview.html.as_uri())`; dosya yoksa hata)
- `rich` ilerleme çubuğu + sonda özet tablo (rol, kaynak, kontrast düzeltmeleri). Hata → Türkçe mesaj, `raise typer.Exit(code)`.

## 7. Test beklenti dosyaları — `tests/expected/<fixture>.json` şeması

Fixture-author yazar; testler (builder 3a, 2a) bunları **değiştirmeden** kullanır. Tüm anahtarlar zorunlu değildir; olmayan anahtar test edilmez.
```jsonc
{
  "fixture": "neo_brutalist.html",
  "natural_mode": "light",                       // RawSnapshot.natural_mode
  "dominant_background": "#fffdf2",              // ΔE_OK ≤ 0.03
  "has_color_scheme_query": false,
  "counter_background": null,                    // counter snapshot dominant_background (ΔE ≤ 0.03) veya null (counter yok)
  "colors": {                                    // SiteExtraction.colors.roles; değer hex veya {"any_of": [hex, ...]}
    "background": "#fffdf2",                     // tolerans ΔE_OK ≤ 0.05; yarı saydam kaynaklar background üzerine composite edilmiş beklenir
    "text_primary": "#000000",
    "accent": {"any_of": ["#ffe600", "#ff5fa2"]},
    "border": "#000000"
  },
  "palette_includes": ["#ffe600"],               // palette'te ΔE ≤ 0.05 bir küme olmalı
  "fonts": {
    "body_family": "Courier New",                // Typography.body_family (büyük/küçük harf duyarsız)
    "display_family": null,                      // null -> test edilmez
    "mono_family": "Courier New",
    "body_is_monospace": true
  },
  "components": {                                // Components.<tip>; tolerans px ±1
    "button": {"radius_px": 0, "border_width_px": 3, "border_color": "#000000", "shadow_contains": "4px 4px 0px", "has_backdrop": false},
    "card":   {"radius_px": 0, "border_width_px": 3, "has_shadow": true},
    "input":  {"radius_px": 0}
  },
  "shadow_style": "hard",                        // Components.shadow_style
  "hover": {"button": {"transform_changes": true, "background_changes": null, "shadow_changes": null}},  // null -> test edilmez
  "tokens": {"include": ["--accent"], "exclude_prefixes": ["--tw-"]},   // mine_tokens isimleri
  "gradients_min": 0,                            // en az bu kadar gradient
  "spacing_base": 8,
  "container_max_width_px": 1200,                // ±1, null -> test edilmez
  "breakpoints_include": [768],                  // Layout.breakpoints içinde olmalı
  "overlays": {"cookie_banner_removed": false, "header_position": null}  // header_position: header elementinin computed position'ı (örn 'sticky')
}
```
Not: Computed style'da `box-shadow` Chrome'da `rgb(0, 0, 0) 4px 4px 0px 0px` biçimindedir; `shadow_contains` bu biçimdeki bir alt dizedir (örn. `"4px 4px 0px"`).

## 8. Örnek veri dosyaları
- `tests/fixtures/sample_snapshot.json`: geçerli `RawSnapshot` (models ile `model_validate_json` geçer), ~40-80 element; buton, input, kart, başlıklar, p, code, border'lı ve gölgeli kutular, `:root` token'ları (+ `--tw-*` gürültü), 1 gradient, 2+ media query, @font-face.
- `tests/fixtures/sample_design_system.json`: geçerli `DesignSystem` (light+dark kontrast kurallarını SAĞLAYAN renklerle) — generator'lar bununla test edilir.
- `tests/fixtures/snapshots/<fixture>.capture.json`: builder 2a'nın `scripts/regen_fixture_snapshots.py` ile fixture HTML'lerden ürettiği `RawCapture`'lar (commit edilir; miner/blender testleri tarayıcısız bunları kullanır).

## 9. Faz 6 eklemeleri (reviewer bulguları)
- `MotionSystem.measured`, `LayoutSystem.container_measured` / `grid_measured`: blender varsayılan değer kullandığında False yapar; DESIGN.md bu durumda o konuda "ölçüldü" kanıtlı kural YAZMAZ.
- `ComponentSpec.hover.transform` ve `MotionSystem.hover_transform` okunur biçimdedir: `matrix(1,0,0,1,tx,ty)` → `translate(txpx, typx)`, `matrix(s,0,0,s,0,0)` → `scale(s)`, karışıklar `translate(..) scale(..)`; çözülemeyen matrix ham kalır.
- `ring`, background ve surface'e karşı ≥ 3:1 (UI elemanı kuralı). `accent` marka dolgu rengidir; okunurluğu accent-foreground ile sağlanır, kendisi kaydırılmaz (DECISIONS D19).
- Çıktılarda (DESIGN.md, preview, CLI tablosu) yerel kaynaklar mutlak yol yerine dosya adıyla gösterilir (`file:///…/a.html` → `a.html`, `fixture://a.html` → `a.html`). `DesignSystem.sources[].source` ve blend-report ham konumu korur.
