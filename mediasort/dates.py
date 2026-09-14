"""Résolution de la date d'un média : métadonnées, nom de fichier, système."""

import datetime
import re

# Capture AAAA MM JJ avec séparateurs optionnels (-, _, .).
_FILENAME_DATE_RE = re.compile(
    r"((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
)


def date_from_filename(name: str) -> "datetime.date | None":
    """Extrait la première date valide encodée dans le nom, sinon None."""
    for match in _FILENAME_DATE_RE.finditer(name):
        annee, mois, jour = (int(g) for g in match.groups())
        try:
            return datetime.date(annee, mois, jour)
        except ValueError:
            continue
    return None
