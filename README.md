# DesignDNA

DesignDNA, bir veya birden çok web sitesinin (ya da yerel `.html` dosyasının) tasarım DNA'sını çıkarır, ağırlıklarla **harmanlar** ve üretime hazır tasarım dosyaları üretir: CSS değişkenleri, Tailwind (v3 ve v4) ve shadcn/ui temaları, W3C Design Tokens, Claude Code'a verilebilecek bir `DESIGN.md` ve tek dosyalık bir önizleme sayfası.

```
extract  ->  blend  ->  generate
(tarayıcı)   (saf Python)   (Jinja2 şablonları)
```

## İçindekiler

- [Mimari](#mimari)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Harmanlama kuralları](#harmanlama-kuralları)
- [Çıktılar](#çıktılar)
- [Claude Code entegrasyonu](#claude-code-entegrasyonu)
- [Testler](#testler)
- [Telif notu](#telif-notu)
- [Bilinen kısıtlar ve kararlar](#bilinen-kısıtlar-ve-kararlar)

## Mimari

| Katman | Paket | Görev |
|---|---|---|
| Extractor | `designdna/extractor/` | `dom_scanner` sayfayı Playwright/Chromium ile tarar (desktop + mobile, mümkünse karşı renk teması); `hover_probe` hover/focus farklarını ölçer. `token_miner`, `color_miner`, `typography_miner`, `layout_miner`, `component_miner` saf Python'dur ve yalnızca ham veriyle çalışır. |
| Synthesizer | `designdna/synthesizer/blender.py` | Kaynakları ağırlıklara göre rollere dağıtır, kuantize eder, WCAG kontrastını sağlar, karşı temayı belirler. |
| Generators | `designdna/generators/` | Yalnızca `DesignSystem` modelini girdi alıp 8 çıktı dosyasını üretir. |
| Cache | `designdna/cache.py` | Her (url, viewport, renk şeması, sürüm) için ham çıkarımı `.designdna/cache/` altında JSON olarak saklar. |

Önemli noktalar:

- **Tarayıcıya yalnızca `dom_scanner` ve `hover_probe` dokunur.** Miner'lar, blender ve generator'lar tarayıcısızdır.
- `blend` yalnızca cache veya verilen `.capture.json` dosyalarını okur; tarayıcı açmaz ve internete çıkmaz.
- Çıktılar deterministiktir (rastgelelik, zaman damgası yoktur).
- Dosya yolları `pathlib.Path` ile işlenir; Windows ve Linux/WSL üzerinde çalışır.

## Kurulum

Gereksinim: **Python 3.10 veya üzeri**.

### Linux / WSL

```bash
git clone <depo-adresi> designdna && cd designdna
python3 -m venv .venv
source .venv/bin/activate
pip install -e .          # testler için: pip install -e ".[dev]"
playwright install chromium
designdna --help
```

### Windows (PowerShell)

```powershell
git clone <depo-adresi> designdna; cd designdna
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .          # testler için: pip install -e ".[dev]"
playwright install chromium
designdna --help
```

PowerShell betik çalıştırmayı engelliyorsa: `Set-ExecutionPolicy -Scope Process RemoteSigned`.

### Chromium bulunamazsa (yedek yol)

`playwright install chromium` ağ kısıtı vb. nedenle başarısız olursa DesignDNA sistemdeki bir Chrome/Chromium'u kullanır. Tarama (`extract`/`run`) sırasıyla şunları dener (`designdna/utils/browser.py`):

1. Playwright'ın kendi Chromium'u.
2. `DESIGNDNA_CHROMIUM` ortam değişkeninin gösterdiği yürütülebilir dosya.
3. `PATH` içinde `chromium`, `chromium-browser`, `google-chrome`, `google-chrome-stable`, `chrome`.
4. Bilinen yollar: `/opt/pw-browsers/chromium`, `/usr/bin/chromium`, `/usr/bin/chromium-browser`, Windows'ta `C:\Program Files\Google\Chrome\Application\chrome.exe`, `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`, `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`.

Hiçbiri bulunamazsa anlaşılır bir hata ve sıfırdan farklı çıkış kodu alırsınız. Elle yol vermek için:

```bash
export DESIGNDNA_CHROMIUM=/usr/bin/chromium            # Linux/WSL
```
```powershell
$env:DESIGNDNA_CHROMIUM = "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

`blend` ve `preview` komutları tarayıcı gerektirmez.

## Kullanım

Dört komut vardır: `extract`, `blend`, `run`, `preview`.

### Kaynak biçimi: `konum@ağırlık`

- Konum bir URL (`https://...`), `file://` URI'si veya yerel dosya yolu olabilir. Yerel yollar otomatik olarak `file://` URI'ye çevrilir.
- Ağırlık, **son `@` işaretinden sonra** gelen **pozitif bir sayıdır** (`@0.7`, `@3`). Aksi halde `@` konumun parçası sayılır:
  - `https://site.com/@kullanici` -> `@` sonrası sayı değil, tümü konumdur.
  - `ornek@0` -> `0` pozitif ağırlık değildir, `@0` konumun parçası kalır (ağırlık verilmemiş sayılır).
  - `C:\yol\sayfa.html@0.3` -> Windows yolu, ağırlık 0.3.
- Ağırlıklar toplamı 1'e normalize edilir (`@7` ve `@3`, `@0.7` ve `@0.3` ile aynıdır).
- Hiç ağırlık verilmezse kaynaklar **eşit** dağıtılır. Bazılarına verilip bazılarına verilmezse, verilmeyenler verilenlerin ortalamasını alır (DECISIONS D16).

### `extract`: ham çıkarım ve cache

```bash
designdna extract --source "https://site1.com@0.7" --source "https://site2.com@0.3"
designdna extract -s "C:\yol\sayfa.html@0.3" --refresh
designdna extract -s https://site1.com --cache-dir ./benim-cache
```

- `--source / -s` (tekrarlanabilir, en az bir tane gerekir)
- `--refresh`: cache'i yok sayıp yeniden tarar
- `--cache-dir`: varsayılan `./.designdna/cache`

Zaten hazır bir `.capture.json` verilirse taranmaz ("atlandı").

### `blend`: harmanla ve dosyaları üret

```bash
designdna blend -s "https://site1.com@0.7" -s "https://site2.com@0.3" --output ./dist
```

- `--output / -o`: çıktı klasörü (varsayılan `dist`)
- `--cache-dir`: cache klasörü
- Cache'te yoksa: `... için cache bulunamadı, önce designdna extract çalıştırın.`
- `.capture.json` dosyaları doğrudan kaynak olarak verilebilir (tarayıcısız, cache'siz):

```bash
designdna blend \
  --source tests/fixtures/snapshots/linear_dark.capture.json@0.7 \
  --source tests/fixtures/snapshots/neo_brutalist.capture.json@0.3 \
  --output ./dist
```

Komut sonunda üç tablo yazdırılır: kaynaklar (girilen/normalize ağırlık, rol alabilir mi), roller (hangi rol hangi kaynaktan, gerekçesiyle) ve kontrast düzeltmeleri (önce/sonra oran). Ardından karşı temanın `yakalandı` mı `türetildi` mi olduğu ve yazılan dosya sayısı gösterilir.

### `run`: `extract` + `blend`

```bash
designdna run --source "https://site1.com@0.7" --source "https://site2.com@0.3" --output ./dist
designdna run -s https://site1.com -s https://site2.com --refresh
```

`extract` ve `blend` seçeneklerinin birleşimini alır (`--source`, `--output`, `--refresh`, `--cache-dir`).

### `preview`: önizlemeyi aç

```bash
designdna preview ./dist
```

`./dist/preview.html` dosyasını varsayılan tarayıcıda açar. Dosya yoksa önce `blend`/`run` çalıştırmanız söylenir.

### Hatalar

Beklenen hatalar (eksik kaynak, bulunamayan dosya, cache yok, tarayıcı yok, geçersiz ağırlık) Türkçe mesaj ve sıfırdan farklı çıkış kodu ile biter. Click'in kendi kullanım hataları (ör. bilinmeyen seçenek) şimdilik İngilizce kalır; bkz. [TODO.md](TODO.md).

## Harmanlama kuralları

Renk ve fontların aritmetik ortalaması **alınmaz**; tasarım **rolleri** kaynaklara dağıtılır.

1. **Normalizasyon:** ağırlıklar toplam 1.0 olacak şekilde ölçeklenir. 1, 2, 3 ve daha fazla kaynak desteklenir.
2. **0.2 eşiği:** normalize ağırlığı 0.2'nin altındaki kaynak rol almaz; rolleri baskın kaynağa düşer ve bu `blend-report.json`'a yazılır. (En yüksek ağırlıklı kaynak her zaman rol alır; DECISIONS D18.)
3. **Rol grupları** (eşiği geçen kaynaklar ağırlık sırasına göre):
   - **Grup 1, 1. kaynak:** `background`, `surface`, `text-primary`, `text-muted`, `border`, gövde fontu (sans/mono), spacing ve layout ölçeği.
   - **Grup 2, 2. kaynak** (yoksa 1.): `accent`, buton/input radius karakteri, hover etkileşim stili.
   - **Grup 3, 3. kaynak** (yoksa 2., o da yoksa 1.): `box-shadow` karakteri, başlık (display) fontu, kart radius'u.
4. **Kuantizasyon:** radius ve spacing standart değerlere oturtulur: `0, 2, 4, 6, 8, 12, 16, 24px` ve `9999px`; 24px'in üstündeki spacing için `32, 40, 48, 64, 80, 96, 128px` (D6).
5. **Kontrast (WCAG AA):**
   - `text-primary` ve `text-muted`, `background` ve `surface` üzerinde en az **4.5:1**.
   - `accent-foreground`, `accent` üzerinde en az **4.5:1**.
   - `border` ve odak göstergesi `ring`, zeminde en az **3:1** (büyük metin de 3:1). `accent` dolgu rengi olarak korunur, kaydırılmaz (D19).
   - Yetersizse Hue ve Chroma korunur, yalnızca OKLCH **L** kanalı ±0.02 adımlarla (en fazla 40 adım) kaydırılır; her adımda gamut mapping uygulanır. Hedefe ulaşılamazsa beyaz/siyah yönünde en yakın geçerli değer seçilir ve uyarı yazılır. Düzeltmeler `blend-report.json` içinde `contrast_fixes` olarak kayıtlıdır.
6. **Karşı tema:** baskın kaynakta tarama sırasında gerçek bir karşı tema (light/dark) yakalandıysa o kullanılır (`counter_theme: "captured"`); yoksa türetilir (`"derived"`): dark için `background` L 0.12-0.16, `surface` L 0.18-0.22 bandına çekilir, metinler ters çevrilir, aşırı canlı renklerin Chroma'sı kısılır; light için tersi. Sonuç aynı kontrast kontrollerinden geçer.
7. **Kanıtsız kural yok:** ölçülemeyen alanlar (ör. motion, container, grid) varsayılan değerlerle doldurulur ve `DESIGN.md` bunlar için kural yazmaz (D21).

## Çıktılar

`blend`/`run` çıktı klasörüne 8 dosya yazar. Aşağıdaki parçalar, `linear_dark` (%70) ve `neo_brutalist` (%30) örnek kaynaklarının gerçek çıktısından kısaltılmıştır.

### `variables.css`
Light tema `:root` altında, dark tema `.dark` ve `[data-theme="dark"]` altında; renk, font, radius, shadow, spacing, motion ve layout değişkenleri.

```css
:root {
  --color-background: #f5f5f8;
  --color-accent: #ffe600;
  --font-sans: Inter, -apple-system, "Segoe UI", sans-serif;
  --radius-md: 0px;
  --shadow-md: rgb(0, 0, 0) 4px 4px 0px 0px;
  --spacing-2: 16px;
  --container-max-width: 1100px;
}
.dark, [data-theme="dark"] { --color-background: #0a0a0c; /* ... */ }
```

### `tailwind.config.js` (Tailwind v3)
Renkler `variables.css` değişkenlerine bağlanır; `darkMode` `.dark` / `[data-theme="dark"]` ile çalışır; breakpoint'ler yazılır.

```js
darkMode: ["selector", '&:where(.dark, .dark *, [data-theme="dark"], [data-theme="dark"] *)'],
theme: { extend: { colors: { "accent": "var(--color-accent)", /* ... */ } } }
```

### `tailwind-v4.css`
`@theme` bloğu ve `@custom-variant dark`. Kullanım: `@import "tailwindcss"; @import "./tailwind-v4.css";`

```css
@theme {
  --color-background: #f5f5f8;
  --color-accent: #ffe600;
}
```

### `shadcn-theme.css`
shadcn/ui değişken adlarıyla (`--background`, `--foreground`, `--card`, `--primary`, `--muted-foreground`, `--destructive`, `--border`, `--input`, `--ring`, `--radius` vb.), light ve dark için oklch değerleri.

```css
:root {
  --background: oklch(0.971 0.004 286.33);
  --primary: oklch(0.917 0.192 101.41);
}
```

### `tokens.json` (W3C DTCG)
Her token `$value` ve `$type` içerir; renkler `color.light.*` / `color.dark.*` altındadır.

```json
{ "color": { "light": { "background": { "$value": "#f5f5f8", "$type": "color" } } } }
```

### `DESIGN.md`
Başka projelerde Claude Code'a verilmek üzere **İngilizce**, en fazla 300 satırlık tasarım rehberi: kaynaklar ve roller, token özeti, **kanıtlı Do's and Don'ts** (ölçülen veriye dayanır) ve buton/input/kart/navbar/hero için örnek HTML + Tailwind. Örnek kural:

```
- Do: Give cards a 3px solid border (`--color-border`). Evidence: 100% of 8 sampled cards have a border.
```

### `preview.html`
Harici bağımlılığı olmayan tek dosya: renk paleti (hex + kontrast oranı), tipografi hiyerarşisi, hero, istatistik kartları, form elemanları, buton durumları ve sağ üstte light/dark geçiş butonu. Baz tema dark ise sayfa `class="dark"` ile açılır.

### `blend-report.json`
Harmanlamanın denetim kaydı: `sources` (girilen ve normalize ağırlık, `eligible`), `roles` (rol, kaynak, gerekçe), `contrast_fixes`, `counter_theme` (`captured`/`derived`), `warnings`.

```json
{ "role": "accent", "source": "fixture://neo_brutalist.html", "reason": "Grup 2: 2. kaynak (%30)" }
{ "theme": "light", "role": "ring", "original": "#ffe600", "adjusted": "#8f8100",
  "ratio_before": 1.0269, "ratio_after": 3.2058, "target": 3.0, "achieved": true }
```

## Claude Code entegrasyonu

`skill/SKILL.md`, Claude Code'a şunu öğretir: kullanıcı URL'leri ve ağırlıkları verdiğinde (örn. "stripe.com %70, linear.app %30 harmanla") `designdna run` çalıştırır, özet tabloyu aktarır, `DESIGN.md` ve `variables.css` dosyalarını aktif projeye kopyalar ve projenin `CLAUDE.md` dosyasına `Tasarım için DESIGN.md'ye uy` satırını ekler.

### Kurulum

Önce DesignDNA'yı kurun (yukarıdaki [Kurulum](#kurulum)); `designdna` komutu Claude Code'un çalıştırdığı kabuktan erişilebilir olmalı. Sonra skill dosyasını kopyalayın:

**Kullanıcı düzeyinde (tüm projeler):**

```bash
mkdir -p ~/.claude/skills/designdna
cp skill/SKILL.md ~/.claude/skills/designdna/SKILL.md
```
```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills\designdna"
Copy-Item skill\SKILL.md "$env:USERPROFILE\.claude\skills\designdna\SKILL.md"
```

**Yalnızca bir proje için:** aynı dosyayı proje içindeki `.claude/skills/designdna/SKILL.md` konumuna kopyalayın.

Claude Code'u yeniden başlatın; ardından "bu sitelerin tasarımını harmanla" gibi bir istek skill'i tetikler.

## Testler

```bash
pip install -e ".[dev]"
pytest -q
```

- Testler **tamamen offline** çalışır; `file://` fixture'ları ve commit edilmiş snapshot'lar kullanılır.
- `browser` işaretli testler Chromium gerektirir; tarayıcı yoksa **otomatik atlanır**.
- Fixture'lar `tests/fixtures/` altındadır (3 HTML sayfası, `tests/expected/*.json` beklentileri, `tests/fixtures/snapshots/*.capture.json` ham çıkarımlar). Blender ve generator testleri bu snapshot'larla tarayıcısız koşar.
- Snapshot'ları yeniden üretmek için (Chromium gerekir):

```bash
python scripts/regen_fixture_snapshots.py
```

## Telif notu

DesignDNA yalnızca **stil token'larını ve yerleşim kurallarını** (renk, tipografi ölçüsü, boşluk, radius, gölge, bileşen karakteri) alır. Sitelerin metinlerini, görsellerini, logolarını ve markalarını almaz veya üretmez. Üçüncü taraf sitelerden çıkarım yaparken ilgili sitenin kullanım koşullarına ve yerel mevzuata uymak kullanıcının sorumluluğundadır.

## Bilinen kısıtlar ve kararlar

- Bilinen eksikler: [TODO.md](TODO.md)
- Mühendislik kararları ve gerekçeleri: [DECISIONS.md](DECISIONS.md)
