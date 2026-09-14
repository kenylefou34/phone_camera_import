"""Empreinte de contenu d'un fichier (SHA-256), lue par blocs."""

import hashlib
from pathlib import Path

_BLOC = 1024 * 1024  # 1 Mio


def file_hash(path: Path) -> str:
    """Renvoie l'empreinte SHA-256 hexadécimale du contenu du fichier."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloc in iter(lambda: f.read(_BLOC), b""):
            h.update(bloc)
    return h.hexdigest()
