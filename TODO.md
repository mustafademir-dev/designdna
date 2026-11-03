# TODO.md — Bilinen Eksikler

- **HSL kanal üçlüsü token'ları:** shadcn tarzı `--background: 222 47% 11%` gibi `hsl()` sarmalayıcısız değerler token_miner tarafından renk olarak tanınmıyor ve atılıyor. Bu token'lar yine de DOM'daki computed renkler üzerinden renk rollerine yansır; yalnızca "token önceliği" kaybolur.
- **component_miner modül düzeyi önbellek:** `classify_element` snapshot kimliğine (`id()`) göre `_CTX_CACHE` tutar. Zararsız ama kırılgan; ileride açık bir bağlam nesnesine taşınmalı (reviewer #15).
- **Mobile taramanın etkisi sınırlı:** Spec gereği mobile tarama yalnızca layout/breakpoint için kullanılıyor; pratikte çoğu breakpoint desktop stil dosyasından zaten okunuyor. Mobil kolon sayısı/yığılma davranışı ileride `Layout`'a eklenebilir (reviewer #16).
- **Click kullanım hataları İngilizce:** Eksik `--source` Türkçe hata verir, ancak Click/Typer'ın kendi kullanım hataları (ör. bilinmeyen seçenek: `No such option: --bogus`, `--help` metnindeki "Show this message and exit.") İngilizce kalıyor. Doğrulandı: `designdna blend --bogus`.
