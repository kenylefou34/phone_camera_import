"""Configuration du service (surchargeable par variables d'environnement)."""

import os
from pathlib import Path

PORT: int = int(os.environ.get("PORT", "8787"))
LIBRARY_DIR: Path = Path(os.environ.get("LIBRARY_DIR", "/media/izquierdo/Famille"))
CATALOG_DB: Path = Path(os.environ.get("CATALOG_DB", str(Path.home() / "mediasort_catalog.db")))
INCOMING_DIR: Path = Path(os.environ.get("INCOMING_DIR", str(LIBRARY_DIR / "incoming")))
DEVICES_DB: Path = Path(os.environ.get("DEVICES_DB", str(Path.home() / "mediaserve_devices.db")))
SERVICE_TYPE: str = "_mediaserve._tcp"
