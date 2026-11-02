---
name: designdna
description: Kullanıcı bir veya birden çok web sitesi URL'si (ve isteğe bağlı ağırlıklar) verip "bu sitelerin tasarımını harmanla", "şu siteden tasarım sistemi çıkar" dediğinde kullan. DesignDNA ile DESIGN.md, variables.css, Tailwind ve shadcn temaları üretir ve projeye uygular.
---

# DesignDNA ile tasarım harmanlama

## Ön koşullar

```bash
pip install -e .            # DesignDNA deposundan (komut: designdna)
playwright install chromium # yalnızca tarama (extract/run) için gerekir
```

`designdna --help` çalışmıyorsa önce kurulumu tamamlayın.

## Ne zaman

Kullanıcı URL'ler (veya yerel `.html` dosyaları) ve ağırlıklar verdiğinde, örn. "stripe.com %70, linear.app %30 harmanla".
Ağırlık verilmezse kaynaklar eşit dağıtılır; bazıları verilmezse eksikler verilenlerin ortalamasını alır.

## Adımlar

1. Kaynakları `url@ağırlık` biçimine çevirin (ağırlık son `@` sonrasındaki pozitif sayıdır; yüzdeler 0.7 gibi ondalığa çevrilebilir) ve çalıştırın:

   ```bash
   designdna run --source "https://site1.com@0.7" --source "https://site2.com@0.3" --output ./designdna-dist
   ```

   Yerel dosya: `--source "C:\yol\sayfa.html@0.3"`. Cache'i yok saymak için `--refresh` ekleyin.
   Tarama zaten yapıldıysa yalnızca `designdna blend ...` (tarayıcı açmaz, internete çıkmaz).

2. Çıktı özetindeki rol/kaynak tablosunu, kontrast düzeltmelerini ve uyarıları kullanıcıya kısaca aktarın.

3. `./designdna-dist/DESIGN.md` ve `./designdna-dist/variables.css` dosyalarını aktif projeye kopyalayın
   (proje kökü veya projede varsa `src/styles/`). İsteğe bağlı: `tailwind.config.js`, `tailwind-v4.css`, `shadcn-theme.css`, `tokens.json`.

4. Projenin `CLAUDE.md` dosyasına şu satırı ekleyin (dosya yoksa oluşturun, satır zaten varsa tekrar eklemeyin):

   ```
   Tasarım için DESIGN.md'ye uy
   ```

5. İsterseniz `designdna preview ./designdna-dist` ile `preview.html` dosyasını tarayıcıda açın.

## Hata durumları

- "cache bulunamadı": önce `designdna extract --source ...` (veya `run`) çalıştırın.
- "Chromium bulunamadı": `playwright install chromium` çalıştırın ya da `DESIGNDNA_CHROMIUM` ortam değişkenine bir Chrome yolu verin.
- "Ağırlık sıfırdan büyük olmalı": `@0` veya negatif ağırlık geçersizdir.
- "Dosya bulunamadı": yerel yolu kontrol edin.
- Çıkış kodu sıfırdan farklıysa mesajı kullanıcıya aktarın; sessizce devam etmeyin.
