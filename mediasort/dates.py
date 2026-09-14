"""Résolution de la date d'un média : métadonnées, nom de fichier, système."""

import datetime
import json
import re
import subprocess
from collections import namedtuple
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

# Résultat d'une résolution : la date + d'où elle vient.
# source ∈ {"metadata", "filename", "filesystem", "unknown"}
DateResult = namedtuple("DateResult", ["date", "source"])

# Sentinelle "absent" + cache de dates de métadonnées pré-chargées en lot
# (str(chemin) -> date|None). Rempli par prefetch_metadata() pour accélérer les
# gros tris : un seul appel exiftool au lieu d'un par fichier.
_UNSET = object()
_META_CACHE: dict = {}


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


def exiftool_dates_for(paths) -> dict:
    """Lit les dates de métadonnées de plusieurs fichiers en un seul appel exiftool
    par lot. Renvoie {str(chemin): date|None}. Dégradation sûre : {} si exiftool
    échoue (ex. binaire absent)."""
    resultat = {}
    chemins = [str(p) for p in paths]
    taille_lot = 400
    for i in range(0, len(chemins), taille_lot):
        lot = chemins[i:i + taille_lot]
        try:
            sortie = subprocess.run(
                ["exiftool", "-json", "-api", "QuickTimeUTC=1",
                 *[f"-{t}" for t in _METADATA_TAGS], *lot],
                capture_output=True, text=True, timeout=300, check=False,
            )
            donnees = json.loads(sortie.stdout or "[]")
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            donnees = []
        for obj in donnees:
            src = obj.get("SourceFile")
            if src is not None:
                resultat[src] = _pick_metadata_date(obj)
    return resultat


def prefetch_metadata(paths) -> None:
    """Pré-charge (en lot) les dates de métadonnées dans le cache, pour éviter un
    appel exiftool par fichier lors du tri."""
    global _META_CACHE
    _META_CACHE = exiftool_dates_for(paths)


def date_from_metadata(path: Path) -> "datetime.date | None":
    """Date de prise de vue (métadonnées). Consulte d'abord le cache pré-chargé."""
    en_cache = _META_CACHE.get(str(path), _UNSET)
    if en_cache is not _UNSET:
        return en_cache
    return _pick_metadata_date(_exiftool_tags(path))


def date_from_filesystem(path: Path) -> "datetime.date | None":
    """Date de dernière modification du fichier, ou None s'il est illisible."""
    try:
        horodatage = path.stat().st_mtime
    except OSError:
        return None
    return datetime.date.fromtimestamp(horodatage)


def resolve_date(path: Path) -> DateResult:
    """Résout la date selon la priorité : métadonnées > nom > système > inconnue."""
    d = date_from_metadata(path)
    if d is not None:
        return DateResult(d, "metadata")
    d = date_from_filename(path.name)
    if d is not None:
        return DateResult(d, "filename")
    d = date_from_filesystem(path)
    if d is not None:
        return DateResult(d, "filesystem")
    return DateResult(None, "unknown")
