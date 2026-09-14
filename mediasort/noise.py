"""Détection et suppression sûre du bruit résiduel après tri."""

from pathlib import Path

from . import config


def is_noise(path: Path) -> bool:
    """Vrai si le fichier est du bruit connu (jamais un vrai média)."""
    nom = path.name
    if nom.startswith("._"):          # fichiers AppleDouble (macOS)
        return True
    if nom == ".nomedia":
        return True
    return path.suffix.lower() in config.NOISE_EXTS


def clean_noise(root: Path, dry_run: bool) -> "list[Path]":
    """Repère (et supprime si dry_run=False) le bruit sous 'root'. Renvoie la liste."""
    trouves: "list[Path]" = []
    for p in root.rglob("*"):
        if p.is_file() and is_noise(p):
            trouves.append(p)
            if not dry_run:
                p.unlink()
    return trouves
