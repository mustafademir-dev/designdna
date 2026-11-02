# TODO.md — Bilinen Eksikler

- **HSL kanal üçlüsü token'ları:** shadcn tarzı `--background: 222 47% 11%` gibi `hsl()` sarmalayıcısız değerler token_miner tarafından renk olarak tanınmıyor ve atılıyor. Bu token'lar yine de DOM'daki computed renkler üzerinden renk rollerine yansır; yalnızca "token önceliği" kaybolur.
