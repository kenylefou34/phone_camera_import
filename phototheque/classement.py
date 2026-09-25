"""Classement d'un média pour la galerie : type, origine, année/mois/jour.

Lecture seule : ce module ne touche ni au disque ni au catalogue. Tout se
déduit du chemin rangé et, quand le catalogue la connaît, de la date de prise
de vue.

Pourquoi pas seulement le chemin ? Parce que 17 % de la bibliothèque (mesure
du 25/09) n'est pas rangée au format « Photos/AAAA/MM MOIS/ » : dossiers
d'événements (« 2014-10 - A&K - Mariage »), sous-dossiers dans un mois,
dossiers sans date (« Documents », « unsorted »). Aucun ne doit disparaître de
la galerie : ce qui n'a pas de date va dans le rayon « Sans date ».
"""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from mediasort.classify import media_type

# Les trois origines proposées par le filtre « Origine ».
APPAREIL, WHATSAPP, AUTRE = "appareil", "whatsapp", "autre"

# « 2014-10-18 » : la forme écrite par le trieur dans `date_prise`.
_DATE_PRISE = re.compile(r"^((?:19|20)\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
# « 2013 » : un dossier d'année.
_ANNEE = re.compile(r"^((?:19|20)\d{2})$")
# « 2014-10 - A&K - Mariage » : événement daté au mois.
_ANNEE_MOIS_NOMME = re.compile(r"^((?:19|20)\d{2})-(0[1-9]|1[0-2])(?:\s|$)")
# « 2003 - Photos Michèle » : événement daté à l'année.
_ANNEE_NOMMEE = re.compile(r"^((?:19|20)\d{2})\s+-\s")
# « 05 MAI », « 10  OCTOBRE », « 02 - CANARIAS » : le dossier qui suit une année.
_MOIS = re.compile(r"^(0[1-9]|1[0-2])(?:\s|$)")


@dataclass(frozen=True, slots=True)
class Classement:
    """Ce que la galerie sait d'un média. `None` = inconnu."""
    type: str            # "photo" ou "video"
    origine: str         # APPAREIL, WHATSAPP ou AUTRE
    annee: int | None
    mois: int | None
    jour: int | None
    source: str          # "date_prise", "chemin" ou "aucune"


def _dossiers(chemin: str, bibliotheque: str) -> tuple[str, ...]:
    """Les dossiers du chemin, relatifs à la bibliothèque, sans le nom du fichier."""
    p = PurePosixPath(chemin)
    try:
        rel = p.relative_to(bibliotheque)
    except ValueError:
        # Hors bibliothèque (ne devrait pas arriver) : on garde tout sauf la racine.
        rel = PurePosixPath(*p.parts[1:]) if p.is_absolute() else p
    return rel.parts[:-1]


def _origine(dossiers: tuple[str, ...]) -> str:
    if any("whatsapp" in d.lower() for d in dossiers):
        return WHATSAPP
    if dossiers and dossiers[0] in ("Photos", "Videos"):
        return APPAREIL
    return AUTRE


def _date_du_chemin(dossiers: tuple[str, ...]) -> tuple[int | None, int | None]:
    """(année, mois) lus dans le premier dossier daté du chemin."""
    for i, d in enumerate(dossiers):
        m = _ANNEE.match(d)
        if m:
            suivant = dossiers[i + 1] if i + 1 < len(dossiers) else ""
            mm = _MOIS.match(suivant)
            return int(m.group(1)), (int(mm.group(1)) if mm else None)
        m = _ANNEE_MOIS_NOMME.match(d)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = _ANNEE_NOMMEE.match(d)
        if m:
            return int(m.group(1)), None
    return None, None


def classer(chemin: str, date_prise: str | None, bibliotheque: str) -> Classement | None:
    """Classe un média ; `None` si ce n'est pas un média affichable."""
    nom = PurePosixPath(chemin).name
    if nom.startswith("._"):
        # Reste AppleDouble laissé par un Mac : des métadonnées, pas un média.
        return None
    type_ = media_type(PurePosixPath(chemin).suffix)
    if type_ is None:
        return None
    dossiers = _dossiers(chemin, bibliotheque)
    origine = _origine(dossiers)
    m = _DATE_PRISE.match(date_prise or "")
    if m:
        annee, mois, jour = (int(g) for g in m.groups())
        return Classement(type_, origine, annee, mois, jour, "date_prise")
    annee, mois = _date_du_chemin(dossiers)
    if annee is not None:
        return Classement(type_, origine, annee, mois, None, "chemin")
    return Classement(type_, origine, None, None, None, "aucune")
