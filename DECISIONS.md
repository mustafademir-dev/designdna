# DECISIONS.md — Mühendislik Kararları

| # | Konu | Karar | Gerekçe |
|---|---|---|---|
| D1 | Chromium | `playwright install chromium` bu ortamda ağ kısıtı nedeniyle başarısız. `designdna.utils.browser.launch_chromium` önce Playwright'ın kendi tarayıcısını, sonra `DESIGNDNA_CHROMIUM`, PATH'teki chromium/chrome ve bilinen yolları (`/opt/pw-browsers/chromium`, Windows Chrome/Edge) dener. | Spec §8: indirilemezse sistem chromium'u `executable_path` ile kullan. Bu ortamda tarayıcı testleri gerçekten koşar. |
| D2 | İskelet kapsamı | Orkestratör `models.py`, `CONTRACTS.md` yanında `errors.py`, `utils/browser.py`, `tests/conftest.py` dosyalarını da yazdı. | Bunlar tüm modüllerin ortak altyapısı; Faz 0'da tarayıcı kontrolünün tek yerde çözülmesi spec gereği. |
| D3 | Karşı tema taraması | Doğal tarama `color_scheme='light'` (tarayıcı varsayılanı) ile yapılır. `prefers-color-scheme` sorgusu varsa `'dark'` ile ikinci desktop taraması yapılır; doğal modu ilk taramadan farklıysa karşı tema kabul edilir. | Playwright varsayılanı light; aynı modu veren tarama "karşı tema" değildir. |
| D4 | Cache birimi | Her (url, viewport, color_scheme) ayrı `CacheEntry` dosyası; `RawCapture` bunlardan birleştirilir. Hover listesi desktop girdisinde tutulur. | Spec'teki `key = sha256(url + viewport + color_scheme + sürüm)` tanımına birebir uyum. |
| D5 | Fixture snapshot'ları | Fixture HTML'lerinden üretilen `RawCapture` JSON'ları `tests/fixtures/snapshots/` altına commit edilir (`scripts/regen_fixture_snapshots.py`). | Miner/blender testleri tarayıcısız ve hızlı koşar (spec §8). |
| D6 | Spacing kuantizasyonu | ≤24px değerler `{0,2,4,6,8,12,16,24}`'e, >24px değerler `{32,40,48,64,80,96,128}`'e oturtulur. Radius >40px → `9999px`. | Spec yalnızca 24px'e kadar ölçek veriyor; daha büyük bölüm boşlukları da gerekli. |
| D7 | Ek komut bayrağı | CLI'ye `--cache-dir` seçeneği eklendi (varsayılan `./.designdna/cache`). | Testlerde izole cache dizini için. |
| D8 | color_math yuvarlama | `rgb_to_hex` `floor(x*255+0.5)` kullanır; alpha 8-bit'e kuantize edilmez (rgba(255,255,255,0.08)/#0a0a0c → #1e1e1f, ±1). `color(srgb …)` ve açı birimleri de parse edilir. | Deterministik eşitlik çözümü; tarayıcıyla ±1 kanal uyumu. |
| D9 | Fixture beklentileri | Belirsiz kalan değerler (text_muted, surface, bazı border_color'lar) beklenti JSON'larına konmadı; stripe_clean text_primary `any_of` [#0a2540, #425466]. Tüm fixture'lar 8px tabanlı spacing. | Yanlış beklenti, eksik beklentiden kötüdür (fixture-author kuralı). |
