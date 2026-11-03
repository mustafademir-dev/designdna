"""Kullanıcıya gösterilecek hatalar. Mesajlar Türkçedir."""


class DesignDNAError(Exception):
    """CLI tarafından yakalanıp Türkçe mesaj + sıfırdan farklı çıkış koduyla gösterilen hata."""

    exit_code: int = 1

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class SourceParseError(DesignDNAError):
    """--source değeri çözümlenemedi."""


class CacheMissError(DesignDNAError):
    """blend için cache'te kayıt bulunamadı."""


class BrowserUnavailableError(DesignDNAError):
    """Chromium bulunamadı veya başlatılamadı."""
