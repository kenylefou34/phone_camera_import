"""Empreinte de contenu d'un fichier (SHA-256), lue par blocs."""

import hashlib
import shutil
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


def copy_and_hash(source: Path, destination: Path) -> str:
    """Copie 'source' vers 'destination' en calculant l'empreinte au passage.

    La source n'est lue qu'UNE seule fois : chaque bloc est à la fois haché et
    écrit. Cela épargne une traversée complète du fichier par rapport à
    « file_hash() puis shutil.copy2() » — décisif sur les vidéos de plusieurs
    gigaoctets (issue #14).

    Les métadonnées sont recopiées comme le ferait shutil.copy2(). Ce n'est pas
    cosmétique : la date de modification sert de dernier recours à la datation
    (voir dates.date_from_filesystem).

    Renvoie l'empreinte SHA-256 des octets lus dans la source.
    """
    h = hashlib.sha256()
    with open(source, "rb") as f_source, open(destination, "wb") as f_destination:
        for bloc in iter(lambda: f_source.read(_BLOC), b""):
            h.update(bloc)
            f_destination.write(bloc)
    shutil.copystat(source, destination)
    return h.hexdigest()
