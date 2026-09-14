"""Résolution de la date d'un média : métadonnées, nom de fichier, système."""

import datetime
import json
import re
import subprocess
from pathlib import Path

# Capture AAAA MM JJ avec séparateurs optionnels (-, _, .).
_FILENAME_DATE_RE = re.compile(
    r"((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
)

# Ordre de préférence des balises de date renvoyées par exiftool.
_METADATA_TAGS = [
    "DateTimeOriginal",   # photos
    "CreateDate",         # photos et vidéos
    "CreationDate",       # vidéos (QuickTime)
    "MediaCreateDate",    # vidéos
]


def date_from_filename(name: str) -> "datetime.date | None":
    """Extrait la première date valide encodée dans le nom, sinon None."""
    for match in _FILENAME_DATE_RE.finditer(name):
        annee, mois, jour = (int(g) for g in match.groups())
        try:
            return datetime.date(annee, mois, jour)
        except ValueError:
            continue
    return None


def _pick_metadata_date(tags: dict) -> "datetime.date | None":
    """Choisit la meilleure date parmi les balises exiftool (ordre de préférence)."""
    for cle in _METADATA_TAGS:
        valeur = tags.get(cle)
        if not valeur:
            continue
        # Format attendu : "AAAA:MM:JJ hh:mm:ss" (parfois avec fuseau derrière).
        debut = str(valeur)[:10]  # "AAAA:MM:JJ"
        try:
            annee, mois, jour = (int(x) for x in debut.split(":"))
            return datetime.date(annee, mois, jour)
        except (ValueError, TypeError):
            continue
    return None


def _exiftool_tags(path: Path) -> dict:
    """Interroge exiftool et renvoie un dict de balises (vide en cas d'échec)."""
    try:
        sortie = subprocess.run(
            ["exiftool", "-json", "-api", "QuickTimeUTC=1",
             *[f"-{t}" for t in _METADATA_TAGS], str(path)],
            capture_output=True, text=True, timeout=30, check=False,
        )
        donnees = json.loads(sortie.stdout or "[]")
        return donnees[0] if donnees else {}
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return {}


def date_from_metadata(path: Path) -> "datetime.date | None":
    """Renvoie la date de prise de vue lue dans les métadonnées, sinon None."""
    return _pick_metadata_date(_exiftool_tags(path))
