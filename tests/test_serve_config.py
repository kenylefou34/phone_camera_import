import importlib
from pathlib import Path


def test_config_defaults(monkeypatch):
    for v in ("PORT", "LIBRARY_DIR", "CATALOG_DB", "INCOMING_DIR", "DEVICES_DB"):
        monkeypatch.delenv(v, raising=False)
    cfg = importlib.reload(importlib.import_module("phototheque.config"))
    assert cfg.PORT == 8787
    assert isinstance(cfg.LIBRARY_DIR, Path)


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("LIBRARY_DIR", "/tmp/lib")
    cfg = importlib.reload(importlib.import_module("phototheque.config"))
    assert cfg.PORT == 9999
    assert str(cfg.LIBRARY_DIR) == "/tmp/lib"


def test_public_url_uses_the_real_hostname(monkeypatch):
    """L'URL publiée : le nom d'hôte réel, et le schéma https (issue #3).

    Régression : l'URL était figée à « http://nuc.local:8787 », qui ne résout
    pas — la machine s'annonce en mDNS sous IZQUIERDO-NUC.local. Le QR code
    d'appairage encodait donc une adresse injoignable pour l'app.

    Le schéma est vérifié ici aussi : le service ne parle plus qu'en HTTPS, et
    un QR en « http:// » serait injoignable pour la même raison. (Un second
    test qui n'assertait que cela, avec exactement la même préparation, a été
    fusionné ici.)
    """
    import importlib, socket
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: "ESSAI-HOTE")
    cfg = importlib.reload(importlib.import_module("phototheque.config"))
    assert cfg.PUBLIC_URL == "https://ESSAI-HOTE.local:8787"


def test_public_url_can_be_overridden(monkeypatch):
    """Surchargeable : nom personnalisé, autre port, ou variante Docker (HTTP)."""
    import importlib
    monkeypatch.setenv("PUBLIC_URL", "https://photos.maison:8443")
    cfg = importlib.reload(importlib.import_module("phototheque.config"))
    assert cfg.PUBLIC_URL == "https://photos.maison:8443"


def test_chemins_du_certificat_par_defaut(monkeypatch):
    """Certificat et clé vivent dans ~/.config/phototheque/."""
    import importlib
    from pathlib import Path
    monkeypatch.delenv("CERT_FILE", raising=False)
    monkeypatch.delenv("KEY_FILE", raising=False)
    cfg = importlib.reload(importlib.import_module("phototheque.config"))
    assert cfg.CERT_FILE == Path.home() / ".config" / "phototheque" / "cert.pem"
    assert cfg.KEY_FILE == Path.home() / ".config" / "phototheque" / "key.pem"

