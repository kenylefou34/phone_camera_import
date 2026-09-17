"""Configuration du service (surchargeable par variables d'environnement)."""

import os
import socket
from pathlib import Path

PORT: int = int(os.environ.get("PORT", "8787"))
LIBRARY_DIR: Path = Path(os.environ.get("LIBRARY_DIR", "/media/izquierdo/Famille"))
CATALOG_DB: Path = Path(os.environ.get("CATALOG_DB", str(Path.home() / "mediasort_catalog.db")))
INCOMING_DIR: Path = Path(os.environ.get("INCOMING_DIR", str(LIBRARY_DIR / "incoming")))
DEVICES_DB: Path = Path(os.environ.get("DEVICES_DB", str(Path.home() / "phototheque_devices.db")))

# Secrets et certificat du service. Dossier créé par deploy/install.sh en 0700,
# fichiers en 0600 : la clé privée ne doit être lisible que par le service.
CONFIG_DIR: Path = Path(os.environ.get(
    "CONFIG_DIR", str(Path.home() / ".config" / "phototheque")))
CERT_FILE: Path = Path(os.environ.get("CERT_FILE", str(CONFIG_DIR / "cert.pem")))
KEY_FILE: Path = Path(os.environ.get("KEY_FILE", str(CONFIG_DIR / "key.pem")))
ADMIN_FILE: Path = Path(os.environ.get("ADMIN_FILE", str(CONFIG_DIR / "admin")))

SERVICE_TYPE: str = "_phototheque._tcp"

# Adresse publiée dans le QR d'appairage et sur la page d'admin. Elle est
# déduite du nom d'hôte réel : c'est sous « <nom>.local » qu'Avahi annonce la
# machine sur le réseau. Un nom écrit en dur (« nuc.local ») ne résout pas et
# rendrait le QR inutilisable par l'app. Surchargeable par PUBLIC_URL, par
# exemple pour passer en HTTPS (issue #3).
PUBLIC_URL: str = os.environ.get(
    "PUBLIC_URL", f"https://{socket.gethostname()}.local:{PORT}"
)
