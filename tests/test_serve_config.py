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
