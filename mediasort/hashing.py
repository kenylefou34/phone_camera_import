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


def quick_signature(path: Path, chunk: int = 65536) -> str:
    """Signature RAPIDE d'un fichier : taille + hash du début et de la fin.

    Sert de PRÉ-FILTRE bon marché (éviter de hacher entièrement de grosses
    vidéos) — ce n'est PAS une clé d'unicité (collisions possibles). Non encore
    branchée sur le catalogue/dédup : voir issue #9 (décision de schéma requise).
    """
    taille = path.stat().st_size
    h = hashlib.sha256()
    h.update(str(taille).encode())
    with open(path, "rb") as f:
        h.update(f.read(chunk))
        if taille > chunk:
            f.seek(max(0, taille - chunk))
            h.update(f.read(chunk))
    return h.hexdigest()
