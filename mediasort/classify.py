"""Décision du chemin de destination d'un média dans la bibliothèque."""

import re
from pathlib import Path

from . import config

# Un dossier "standard" est soit une année (ex. 2023), soit "MM MOIS" (ex. 05 MAI).
_ANNEE_RE = re.compile(r"^(?:19|20)\d{2}$")
_MOIS_RE = re.compile(r"^(0[1-9]|1[0-2]) [A-ZÉÈ]+$")


def media_type(ext: str) -> "str | None":
    """Renvoie 'photo', 'video' ou None selon l'extension (insensible à la casse)."""
    e = ext.lower()
    if e in config.PHOTO_EXTS:
        return "photo"
    if e in config.VIDEO_EXTS:
        return "video"
    return None


def is_whatsapp(path: Path) -> bool:
    """Vrai si l'un des dossiers du chemin évoque WhatsApp."""
    return any("whatsapp" in part.lower() for part in path.parts)


def is_excluded(path: Path) -> bool:
    """Vrai si le chemin traverse un sous-dossier WhatsApp exclu."""
    parts = set(path.parts)
    return any(excl in parts for excl in config.WHATSAPP_EXCLUDES)


def is_curated_folder(name: str) -> bool:
    """Vrai si le dossier n'est PAS un dossier standard (année ou 'MM MOIS')."""
    return not (_ANNEE_RE.match(name) or _MOIS_RE.match(name))


def destination(library: Path, source_file: Path, date_result, mtype: str) -> Path:
    """Calcule le chemin de destination complet du fichier."""
    if date_result.date is None:
        return library / "_A_TRIER" / source_file.name

    racine = library
    if is_whatsapp(source_file):
        racine = racine / "WhatsApp"
    racine = racine / ("Photos" if mtype == "photo" else "Videos")

    annee = f"{date_result.date.year:04d}"
    mois = config.month_folder(date_result.date.month)
    return racine / annee / mois / source_file.name
