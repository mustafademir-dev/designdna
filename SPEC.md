# Görev: DesignDNA — Referans Sitelerden Tasarım Sistemi Çıkarıcı ve Sentezleyici CLI

Python ve Playwright kullanarak, verilen URL'lerin veya yerel HTML dosyalarının tasarım dilini çıkaran, bunları ağırlıklarla harmanlayan ve üretime hazır tasarım çıktıları üreten bir CLI aracı (`designdna`) geliştir.

---

## A. Orkestrasyon Modeli (EN ÖNEMLİ BÖLÜM — önce bunu uygula)

Sen (ana oturum, Opus) **orkestratörsün**. Kodun büyük kısmını sen yazmayacaksın; işi alt ajanlara bölüp yöneteceksin. Amaç: ana bağlamın kod dosyalarıyla dolmaması.

### A1. Alt ajan kurulumu
- İşe başlamadan `.claude/agents/` altına şu alt ajan tanımlarını yaz (frontmatter'da `model: sonnet`):
  - `builder.md`: Kendisine verilen modülü ve testlerini yazar, testleri koşar, düzeltir.
  - `fixture-author.md`: Test fixture HTML'lerini ve beklenen değer JSON'larını yazar. Extractor koduna asla bakmaz.
  - `fixer.md`: Verilen hata çıktısını ve ilgili dosyaları alıp hatayı düzeltir.
  - `reviewer.md`: Kodu üretimine katılmamış biri olarak bu spec'e göre denetler, bulguları listeler, kod değiştirmez.
- Alt ajanları bu tanımlarla ya da çağırırken `model: "sonnet"` vererek başlat. Opus'u yalnızca orkestrasyon, sözleşme tasarımı ve sonuçları değerlendirme için kullan.

### A2. Orkestratörün kuralları
- **Kaynak kodu baştan sona okuma.** Alt ajanların özet raporlarıyla çalış. Bir dosyayı yalnızca entegrasyon hatası gerektirdiğinde ve yalnızca ilgili kısmını oku.
- Kendin yazdığın kod yalnızca: proje iskeleti, `pyproject.toml`, `designdna/models.py` (Pydantic sözleşmeleri) ve `CONTRACTS.md`.
- **Sözleşmeleri yalnızca sen değiştirirsin.** Bir alt ajan sözleşme değişikliği isterse sen karar verirsin, `models.py` ve `CONTRACTS.md`'yi güncellersin, etkilenen alt ajanlara bildirirsin.
- Bağımsız işleri **paralel** başlat.
- Durumu `PROGRESS.md` dosyasında tut: faz, biten modüller, açık hatalar, alınan kararlar. Bağlam sıkıştırılırsa bu dosyadan devam et.

### A3. Alt ajana verilecek görev paketi
Her alt ajan görevinde şunlar olsun:
1. Bu spec'in yalnızca ilgili bölümü (tamamı değil).
2. `CONTRACTS.md` ve `designdna/models.py` yolu.
3. **Sahiplik:** Düzenleyebileceği dosyaların listesi. Başka dosyaya dokunmaz.
4. Çalıştıracağı test komutu, örn. `pytest tests/test_color_math.py -q`.
5. Rapor formatı, en fazla 200 kelime: değişen dosyalar, public fonksiyon imzaları, test sonucu (geçen/kalan), aldığı kararlar, sözleşme değişikliği talebi varsa o.

### A4. Döngü sınırları
- Aynı hata 3 kez düzeltilemezse farklı bir yaklaşım dene.
- 5 denemede de çözülmezse sorunu `TODO.md`'ye yaz ve devam et. Tek bir hatada takılıp kalma.

### A5. Fazlar
| Faz | Kim | İş | Paralel |
|---|---|---|---|
| 0 | Orkestratör | İskelet, `pyproject.toml`, `models.py`, `CONTRACTS.md`, `.claude/agents/`, `PROGRESS.md` | — |
| 1 | builder | `utils/color_math.py` + testleri | ✔ |
| 1 | fixture-author | 3 fixture HTML + `tests/expected/*.json` + örnek `tests/fixtures/sample_snapshot.json` ve `sample_design_system.json` | ✔ |
| 2 | builder ×3 | (a) `dom_scanner.py` + `hover_probe.py` + cache, (b) `color_miner.py` + `typography_miner.py`, (c) `token_miner.py` + `layout_miner.py` + `component_miner.py` | ✔ |
| 3 | builder ×3 | (a) `blender.py`, (b) tüm generator'lar (`sample_design_system.json` ile çalışır, blender'ı beklemez), (c) CLI + `skill/SKILL.md` | ✔ |
| 4 | Orkestratör + fixer | Tam test paketini koş, her hatayı yalnızca hata çıktısı ve ilgili dosyayla fixer'a ver | — |
| 5 | reviewer | Taze bağlamla tüm projeyi bu spec'e göre denetle, bulguları listele | — |
| 6 | fixer | Reviewer bulgularını düzelt, testleri yeniden koş | ✔ |
| 7 | builder | README (Türkçe), `DECISIONS.md` ve `TODO.md`'nin tamamlanması | — |
| 8 | Orkestratör | Son test koşusu, PR | — |

---

## 0. Çalışma Kuralları
- **Tamamen otonom çalış**, bana soru sorma. Belirsiz bir yer olursa en makul mühendislik kararını seç ve `DECISIONS.md` dosyasına gerekçesiyle yaz.
- **Kapsamı aşma.** Önce çekirdek mimariyi uçtan uca bitir ve testlerden geçir. Kodda placeholder (`TODO`, `pass`, `...`) bırakma; yapamadığın şeyleri yalnızca `TODO.md` dosyasına yaz.
- **Telif/İçerik:** Logo, görsel (img/svg) ya da metin içeriği kopyalama. Sadece stil token'larını ve yapısal (layout) kuralları al.
- **Platform:** `README.md` Türkçe olsun. Dosya yolları `pathlib.Path`, kodlama `utf-8`; hem Windows hem WSL (Linux) üzerinde sorunsuz çalışmalı.
- **Testleri geçirmek için testleri gevşetme, silme veya atlama.** Hata varsa kodu düzelt. `tests/expected/*.json` değerleri yalnızca fixture'da gerçekten hata varsa ve gerekçesi `DECISIONS.md`'ye yazılarak değiştirilebilir.

## 1. Paket Yapısı ve Sözleşmeler
Paket adı: `designdna/`. Araçlar: `pyproject.toml`, `typer`, `pydantic`, `playwright`, `jinja2`, `pytest`, `rich`.

**`designdna/models.py`** (orkestratör yazar) en az şu modelleri içerir:
- `RawSnapshot`: Tek bir tarama sonucu ham veri (elementler, computed style'lar, bounding box'lar, custom property'ler, @font-face, media query'ler, gradient'ler, doğal mod, viewport, color_scheme).
- `HoverDiff`: Bileşen tipi, öncesi/sonrası stil farkı, transition süresi ve easing.
- `SiteExtraction`: Bir kaynağın işlenmiş çıkarımı (renk rolleri, tipografi, spacing, layout, bileşenler, token'lar, karşı tema varsa onun verisi).
- `DesignSystem`: Harmanlanmış nihai sistem (light + dark), generator'ların tek girdisi.
- `BlendReport`: Hangi rolün hangi kaynaktan geldiği, kontrast düzeltmeleri, uyarılar.

**Mimari kural:** Tarayıcıya yalnızca `dom_scanner.py` ve `hover_probe.py` dokunur. Diğer tüm miner'lar `RawSnapshot` alan **saf Python fonksiyonlarıdır**; böylece tarayıcı olmadan `sample_snapshot.json` ile test edilebilir ve paralel geliştirilebilir.

Renk dönüşümleri için harici ağır kütüphane kullanma; `designdna/utils/color_math.py` içinde kendi deterministik dönüşümlerini yaz:
- sRGB ↔ Linear RGB ↔ OKLab ↔ OKLCH, `rgb/rgba/hex/hsl/oklch` parse.
- WCAG kontrast oranı hesaplama.
- **Gamut mapping:** OKLCH → sRGB dönüşümünde renk sRGB dışına taşarsa L'yi sabit tutup Chroma'yı düşürerek gamut içine al.
- Yarı saydam renkleri, altındaki opak arka planla alpha-composite ederek gerçek görünen renge çevir.

## 2. `designdna/extractor/`

**Performans kuralı:** Elementleri tek tek Playwright çağrılarıyla okuma. DOM gezme, `getBoundingClientRect()`, `getComputedStyle()`, stylesheet custom property'leri, `@font-face` ve `@media` okumalarını **tek bir `page.evaluate()` içinde JavaScript fonksiyonu olarak** çalıştır ve Python'a `RawSnapshot` JSON'u döndür.

### `dom_scanner.py`
- Sayfayı desktop (`1440x900`) ve mobile (`375x812`) viewport'larda aç. **Mobile taraması yalnızca layout ve breakpoint verisi için kullanılır**, renk ve token kaynağı olmaz.
- **Yükleme:** `wait_until="domcontentloaded"`, ardından en fazla 3 saniyelik `networkidle` denemesi (timeout olursa hata verme, devam et), sonra `document.fonts.ready`.
- **Lazy-load:** Sayfayı hızlı adımlarla sonuna kadar scroll et (en fazla 10.000px, sonsuz scroll'da takılmasın), sonra en üste dön.
- **Cookie/consent kaldırma:** Yalnızca id/class/metninde `cookie`, `consent` veya `gdpr` geçen elementleri ya da viewport'un %30'undan fazlasını kaplayan `position: fixed` overlay'leri gizle. `header`, `nav` ve `[role="banner"]` elementlerine **asla dokunma**.
- **Görünürlük filtresi:** `display: none`, `visibility: hidden`, `opacity: 0`, genişlik veya yükseklik < 2px olanları at. Kalan elementleri piksel alanına (width × height) göre ağırlıklandır.
- **Doğal mod tespiti:** `body`/`html` arka planı transparan olabileceği için onlara güvenme. Viewport'ta en büyük alanı kaplayan opak arka plan rengini bul, OKLCH L < 0.5 ise dark, değilse light kabul et. Hiç opak arka plan yoksa beyaz kabul et.
- **Karşı tema:** Stil dosyalarında `prefers-color-scheme` sorgusu varsa, context'i karşı şemaya (`color_scheme='dark'` veya `'light'`) geçirip desktop için ikinci bir tarama yap.

### `hover_probe.py`
- Her bileşen tipinden (buton, input, kart) görünür en fazla 5 örnek seç.
- Önce `scrollIntoView` ile görünür yap, `transition-duration` ve `transition-timing-function` değerlerini oku.
- Sonra geçici olarak `*, *::before, *::after { transition: none !important; animation: none !important; }` enjekte et, Playwright'ın gerçek `locator.hover()` metodunu uygula (JS `dispatchEvent(new MouseEvent('mouseover'))` kullanma, CSS `:hover`'ı tetiklemez) ve end-state `transform`, `background-color`, `border-color`, `box-shadow` farkını `HoverDiff` olarak kaydet.
- Ardından geçici stili kaldır.

### `token_miner.py` (saf Python)
- `RawSnapshot` içindeki `:root`, `html`, `body`, `[data-theme]` custom property'lerini (`--*`) işle. (Cross-origin stylesheet hataları `dom_scanner`'ın JS kısmında `try/catch` ile yutulur.)
- Framework gürültüsünü (`--tw-*`, `--wp-*`, `--bs-*` vb.) at. Geçerli renk, boyut (`px`, `rem`), font, radius ve shadow tutan semantik değişkenleri **öncelikli veri kaynağı** olarak kaydet.

### `color_miner.py` (saf Python)
- Tüm renkleri normalize edip OKLCH'ye çevir.
- DOM bağlamına göre rollere ayır: `background`, `surface` (kart/panel içleri), `text-primary`, `text-muted`, `accent` (butonlar, aktif linkler, badge'ler), `border`.
- `background-image` içindeki `linear-gradient` ve `radial-gradient` değerlerini ayrıca kaydet.
- Yakın renkleri OKLab öklid mesafesiyle kümele (ΔE_OK < 0.03 olanları en yüksek ağırlıklı renkte birleştir). **%100 deterministik:** rastgele K-Means kullanma; ağırlığa göre sıralı açgözlü kümeleme kullan, eşitlikte hex değerine göre sırala.

### `typography_miner.py` (saf Python)
- `h1`–`h6`, `p`, `small`, `code`, `button` elementlerinden en sık kullanılan `font-family` (fallback zincirinden ana font), `font-size`, `line-height`, `letter-spacing`, `font-weight` değerlerini çıkar.
- `@font-face` kaynaklarını ve `fonts.googleapis.com` linklerini kaydet.
- Başlık/gövde boyutlarının medyan geometrik oranını hesaplayıp en yakın standart Type Scale oranına (1.125, 1.200, 1.250, 1.333, 1.414, 1.500, 1.618) eşle.

### `layout_miner.py` (saf Python)
- `padding`, `margin`, `gap` değerlerini topla, aykırı değerleri at; sitenin 4px mi 8px mi tabanlı olduğuna karar verip standart spacing ölçeğine oturt.
- Container `max-width`, `grid-template-columns` kolon sayıları, yaygın flex hizalamaları ve `@media (min-width/max-width)` breakpoint'lerini çıkar.

### `component_miner.py` (saf Python)
- Sezgisel tespit: Buton (`button`, `a[class*="btn"]`, `[role="button"]`), Input (`input[type=text|email|search|password]`, `textarea`), Kart (başlık/metin içeren, arka planı, kenarlığı veya gölgesi olan kutular).
- Her biri için `border-radius`, `box-shadow`, `border`, `backdrop-filter`, `padding` al ve `hover_probe` sonuçlarıyla birleştir.

## 3. Cache
- `extract` her kaynağın ham çıkarımını (`RawSnapshot` + `HoverDiff` listesi) `.designdna/cache/<key>.json` dosyasına yazar.
- `key = sha256(url + viewport + color_scheme + araç sürümü)`.
- `--refresh` bayrağı cache'i yok sayıp yeniden tarar.
- `blend` **yalnızca** cache veya verilen JSON dosyalarından okur; tarayıcı açmaz, internete çıkmaz.

## 4. `designdna/synthesizer/blender.py`
- Renk ve fontların aritmetik ortalamasını **alma**; tasarım rollerini ağırlıklara göre dağıt.
- Ağırlıkları toplam 1.0 olacak şekilde normalize et. 1, 2, 3 ve daha fazla kaynakla çalışsın.
- **Eşik:** Ağırlığı 0.2'nin altındaki kaynak rol almaz; o rol baskın kaynağa düşer. Bu durum `blend-report.json`'a yazılır.
- **Rol dağıtımı** (eşiği geçen kaynaklar ağırlık sırasına göre):
  - 1. kaynak: `background`, `surface`, `text-primary`, `text-muted`, `border`, gövde fontu (sans/mono), spacing ve layout ölçeği.
  - 2. kaynak (yoksa 1.): `accent`, buton/input radius karakteri, hover etkileşim stili.
  - 3. kaynak (yoksa 2., o da yoksa 1.): `box-shadow` karakteri, başlık (display) fontu, kart radius.
- Radius ve spacing token'larını her zaman standart değerlere kuantize et: `0, 2, 4, 6, 8, 12, 16, 24px` ve `9999px`.
- **Kontrast (WCAG AA):**
  - `background` ve `surface` üzerindeki `text-primary` ve `text-muted` için en az **4.5:1**.
  - `accent` ile üzerindeki metin (`accent-foreground`) için en az **4.5:1**.
  - `border` ve UI elemanları ile büyük metin (≥24px veya ≥18.66px bold) için en az **3:1**.
  - Yetersizse Hue ve Chroma'yı koruyarak yalnızca OKLCH L kanalını ±0.02 adımlarla kaydır (en fazla 40 adım), her adımda gamut mapping uygula. Hedefe ulaşılamazsa beyaz ya da siyah yönünde en yakın geçerli değeri seç ve uyarı logla.
- **Karşı tema:**
  - Baskın kaynakta tarama sırasında gerçek bir karşı tema yakalandıysa onu kullan.
  - Yoksa türet: dark için `background` L değerini 0.12–0.16, `surface` L değerini 0.18–0.22 bandına çek, metinleri ters çevir, aşırı parlayan renklerin Chroma'sını hafifçe kıs. Light için tersini uygula. Sonucu aynı kontrast kontrollerinden geçir.

## 5. `designdna/generators/` (Jinja2 şablonlarıyla, girdi yalnızca `DesignSystem`)
- **`variables.css`:** Light tema `:root`, dark tema `.dark` ve `[data-theme="dark"]` altında. Renk, font, radius, shadow, spacing, transition değişkenleri.
- **`tailwind.config.js`** (Tailwind v3) ve **`tailwind-v4.css`** (`@theme` bloğu).
- **`shadcn-theme.css`:** shadcn/ui değişken isimleriyle tam uyumlu: `--background`, `--foreground`, `--card`, `--card-foreground`, `--popover`, `--popover-foreground`, `--primary`, `--primary-foreground`, `--secondary`, `--secondary-foreground`, `--muted`, `--muted-foreground`, `--accent`, `--accent-foreground`, `--destructive`, `--border`, `--input`, `--ring`, `--radius`. Light ve dark için.
- **`tokens.json`:** W3C Design Tokens (DTCG) formatında; her token `$value` ve `$type` içersin.
- **`DESIGN.md`:** Başka projelerde Claude Code'a verilecek dosya. İçeriği:
  - Kaynaklar, ağırlıklar ve hangi rolün hangi kaynaktan geldiği.
  - Token özeti (renk, tipografi, spacing, radius, shadow, motion).
  - **Veriye dayalı Do's & Don'ts:** Her kural bir kanıtla birlikte yazılsın (örn. "Kartların %85'inde 1px border var, gölge yok → kartlarda gölge yerine 1px border kullan"). Veride karşılığı olmayan kural yazma.
  - Buton, input, kart, navbar ve hero için örnek HTML + Tailwind kodları.
  - Toplam uzunluk 300 satırı geçmesin.
- **`preview.html`:** Tek dosya, harici bağımlılık yok (fontlar hariç). İçinde: renk paleti (hex + kontrast oranı), tipografi hiyerarşisi, hero alanı, istatistik kartları, form elemanları, buton durumları (normal/hover/disabled) ve sağ üstte light/dark geçiş butonu.
- **`blend-report.json`:** Her rolün hangi kaynaktan geldiği, kontrast düzeltmeleri ve uyarılar.

## 6. CLI
Komutlar:
- `designdna extract --source "https://site.com@0.7" --source "C:\yol\sayfa.html@0.3" [--refresh]`
- `designdna blend --source "https://site.com@0.7" --source "C:\yol\sayfa.html@0.3" --output ./dist`
- `designdna run --source ... --source ... --output ./dist` (extract + blend)
- `designdna preview ./dist` (preview.html'i tarayıcıda açar)

Kurallar:
- Ağırlık, **son `@` işaretinden sonra** parse edilsin; yalnızca `@` sonrası geçerli bir pozitif sayıysa (regex `@(\d+(?:\.\d+)?)$`). Değilse `@` URL/dosya yolunun parçası kabul edilsin. Böylece `https://`, `file://`, `@scope` içeren URL'ler ve Windows yolları (`C:\...`) bozulmasın. Ağırlık verilmezse eşit dağıt.
- Yerel dosya yolları otomatik olarak `file://` URI'ye çevrilsin.
- `rich` ile ilerleme çubuğu ve sonunda özet tablo (roller, kaynaklar, kontrast düzeltmeleri).
- Hatalarda anlaşılır Türkçe mesaj ve sıfırdan farklı çıkış kodu.

## 7. Claude Code Entegrasyonu
`skill/SKILL.md` yaz: Kullanıcı URL'leri ve ağırlıkları verdiğinde `designdna run` çalıştırsın, `DESIGN.md` ve `variables.css` dosyalarını aktif projeye kopyalasın, projenin `CLAUDE.md` dosyasına "Tasarım için DESIGN.md'ye uy" satırını eklesin. Kurulum adımlarını README'ye ekle.

## 8. Testler (`pytest`, tamamen offline)
- **İnternet kullanma.** Tüm testler yerel dosyalarla çalışsın.
- `tests/fixtures/` altına üç farklı sayfa (fixture-author yazar):
  1. `neo_brutalist.html`: radius 0, `3px solid #000` kenarlık, `4px 4px 0 #000` gölge, sarı/pembe vurgu, monospace font, hover'da translate efekti.
  2. `linear_dark.html`: `#0a0a0c` arka plan, `1px rgba(255,255,255,0.08)` kenarlık, 8px radius, Inter tarzı sans-serif, `backdrop-filter: blur`, `:root` custom property'leri, `--tw-*` gürültü değişkenleri.
  3. `stripe_clean.html`: açık ve ferah zemin, `body` arka planı transparan (zemin bir wrapper div'de), çok katmanlı yumuşak gölgeler, 12–16px radius, mor/mavi vurgu, `prefers-color-scheme: dark` desteği, bir cookie banner ve sticky bir `header`.
- Beklenen değerler `tests/expected/*.json` dosyalarında, **extractor yazılmadan önce ve extractor'ı yazmayan bir ajan tarafından** sabitlenir. Testler bu değerlerle toleranslı karşılaştırma yapar.
- Miner testleri tarayıcı gerektirmez; `sample_snapshot.json` ve fixture'lardan üretilmiş snapshot'larla çalışır.
- **Test senaryoları:**
  - `color_math`: bilinen değerlerle dönüşüm doğruluğu, kontrast hesabı, gamut mapping, alpha-composite.
  - Her fixture'ın tek başına doğru parse edilmesi: renkler, roller, radius, gölge, hover farkı, `:root` token'ları, gürültü filtresi, doğal mod tespiti (stripe_clean'in transparan body'sine rağmen light tespit edilmesi), karşı tema taraması.
  - Cookie banner'ın kaldırılması ve sticky header'ın korunması.
  - Harmanlama: %70 linear_dark + %30 neo_brutalist; üç kaynaklı harmanlama; %95/%5 senaryosunda düşük ağırlıklı kaynağın rol almaması.
  - Kontrast: tüm çıktılarda light ve dark için kontrast kurallarının sağlanması (`text-primary` ve `text-muted` ≥ 4.5:1, `accent-foreground` ≥ 4.5:1, `border` ≥ 3:1).
  - Determinizm: aynı girdi iki kez çalıştırılınca birebir aynı çıktı.
  - CLI parse: `https://...@0.7`, `file://...@0.3`, `C:\yol\a.html@0.5`, içinde `@` geçen ağırlıksız kaynak (`C:\user@domain\a.html`).
  - Cache: `blend` komutunun tarayıcı açmadan cache'ten çalışması; `--refresh` davranışı.
  - Çıktılar: tüm dosyaların oluşması, `tokens.json`'ın DTCG şemasına uyması, shadcn değişkenlerinin eksiksiz olması, `DESIGN.md`'nin 300 satırı geçmemesi.
  - **E2E:** `preview.html` Playwright ile açıldığında konsol hatası olmaması, ana bölümlerin görünür olması ve tema geçiş butonunun `.dark` sınıfını değiştirmesi.
- **Playwright Chromium indirilemezse:** sistemde chromium ara (`which chromium chromium-browser google-chrome`) ve `executable_path` ile kullan. O da yoksa yalnızca tarayıcı gerektiren testleri `pytest.mark.skipif` ile işaretle, nedenini `TODO.md`'ye yaz. Tarayıcı gerektirmeyen tüm testler yine de çalışmalı. Bu kontrolü Faz 0'da yap ki sonraki fazlarda kimse bunun için tur harcamasın.

## 9. Bitiş Kriterleri
- Tüm testler geçiyor (tarayıcı yoksa yalnızca tarayıcı testleri gerekçeli skip).
- Reviewer bulgularının tamamı ya düzeltilmiş ya da gerekçesiyle `TODO.md`'de.
- `README.md` (Türkçe: kurulum, kullanım örnekleri, çıktıların açıklaması), `DECISIONS.md`, `TODO.md`, `PROGRESS.md` güncel.
- PR açılmış; PR açıklamasında özet, test sonucu ve bilinen eksikler var.
