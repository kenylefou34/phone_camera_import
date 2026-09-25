"""Modèle d'une page de galerie : ce qu'il faut afficher, sans le HTML.

Séparé de web.py pour être testé sans navigateur : quel niveau (années, mois,
grille), quels liens, quelle page. web.py ne fait que mettre ce modèle en
forme.
"""

from dataclasses import dataclass, field
from datetime import date
from math import ceil
from urllib.parse import urlencode

from .galerie_index import SANS, Filtres, Index, Media

TAILLE_PAGE = 120

MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre")
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


@dataclass
class VueGalerie:
    titre: str
    fil: list[tuple[str, str]]                 # fil d'Ariane : (libellé, url)
    filtres: Filtres
    blocs: list[tuple[str, str, int]]          # (libellé, url, nombre)
    groupes: list[tuple[str, list[Media]]] = field(default_factory=list)
    page: int = 1
    pages: int = 1
    total: int = 0
    precedente: str | None = None
    suivante: str | None = None
    message: str | None = None
    position: dict = field(default_factory=dict)


def lire_filtres(du: str, au: str, type_: str, origine: str) -> tuple[Filtres, str | None]:
    """Traduit les paramètres d'URL. Une valeur inconnue est ignorée, jamais
    une erreur : c'est une page qu'on feuillette, pas un formulaire à corriger."""
    def jour(texte: str) -> date | None:
        try:
            return date.fromisoformat(texte) if texte else None
        except ValueError:
            return None
    debut, fin, message = jour(du), jour(au), None
    if debut and fin and debut > fin:
        debut, fin = fin, debut
        message = "La date de début était après la date de fin : les deux ont été inversées."
    return (Filtres(debut, fin,
                    type_ if type_ in ("photo", "video") else None,
                    origine if origine in ("appareil", "whatsapp", "autre") else None),
            message)


def lire_niveau(valeur: str) -> int | str | None:
    if valeur == SANS:
        return SANS
    try:
        return int(valeur) if valeur else None
    except ValueError:
        return None


def lire_page(valeur: str) -> int:
    """Numéro de page depuis l'URL : une valeur absente, non entière ou
    inférieure à 1 vaut 1 — jamais une erreur (même principe que
    `lire_filtres` : c'est une page qu'on feuillette, pas un formulaire à
    corriger). `construire_vue` ramène de toute façon une page trop grande
    dans les bornes ; ici on ne fait que refuser une valeur absurde."""
    try:
        n = int(valeur)
    except (TypeError, ValueError):
        return 1
    return n if n >= 1 else 1


def url(filtres: Filtres, annee=None, mois=None, jour=None, page=None) -> str:
    """Adresse d'une page de la galerie, filtres compris."""
    params: dict = {}
    for cle, valeur in (("annee", annee), ("mois", mois), ("jour", jour)):
        if valeur is not None:
            params[cle] = valeur
    if filtres.du:
        params["du"] = filtres.du.isoformat()
    if filtres.au:
        params["au"] = filtres.au.isoformat()
    if filtres.type:
        params["type"] = filtres.type
    if filtres.origine:
        params["origine"] = filtres.origine
    if page and page > 1:
        params["page"] = page
    return "/" + ("?" + urlencode(params) if params else "")


def libelle_annee(annee) -> str:
    return "Sans date" if annee == SANS else str(annee)


def libelle_mois(mois) -> str:
    if mois == SANS:
        return "Mois inconnu"
    # Degradation gracieuse pour les valeurs hors limites (URL manipulee) :
    # mois doit etre un entier entre 1 et 12. Sinon, on retourne le numero.
    if isinstance(mois, int) and 1 <= mois <= 12:
        return MOIS[mois - 1].capitalize()
    return str(mois)


def libelle_jour(annee, mois, jour) -> str:
    if jour == SANS:
        return "Jour inconnu"
    try:
        return f"{JOURS[date(annee, mois, jour).weekday()]} {jour}"
    except (ValueError, OverflowError):
        # ValueError : « 30 février ». OverflowError : un jour démesuré venu
        # de l'URL (jour=99999999999999999999), que date() ne sait même pas
        # convertir. Dans les deux cas on garde le numéro, jamais d'erreur 500.
        return str(jour)


def construire_vue(index: Index, filtres: Filtres, annee=None, mois=None,
                   jour=None, page: int = 1, message: str | None = None) -> VueGalerie:
    fil = [("Toutes les années", url(filtres))]

    if annee is None:                                   # accueil : les années
        blocs = [(libelle_annee(a), url(filtres, annee=a), n)
                 for a, n in index.compter_annees(filtres)]
        position = {}
        return VueGalerie("Galerie", fil, filtres, blocs,
                          total=sum(n for _, _, n in blocs), message=message,
                          position=position)

    fil.append((libelle_annee(annee), url(filtres, annee=annee)))
    if annee != SANS and mois is None:                  # une année : ses mois
        blocs = [(libelle_mois(m), url(filtres, annee=annee, mois=m), n)
                 for m, n in index.compter_mois(filtres, annee)]
        position = {"annee": str(annee)}
        return VueGalerie(libelle_annee(annee), fil, filtres, blocs,
                          total=sum(n for _, _, n in blocs), message=message,
                          position=position)

    blocs: list[tuple[str, str, int]] = []
    par_jour = annee != SANS and mois != SANS
    if annee == SANS:
        mois = jour = None                              # le rayon n'a pas de sous-niveau
    elif mois == SANS:
        fil.append(("Mois inconnu", url(filtres, annee=annee, mois=SANS)))
        jour = None
    else:
        fil.append((libelle_mois(mois), url(filtres, annee=annee, mois=mois)))
        jours = index.compter_jours(filtres, annee, mois)
        # Le niveau « jours » n'existe que si au moins un jour est connu (spec §5).
        if any(j != SANS for j, _ in jours):
            blocs = [(libelle_jour(annee, mois, j), url(filtres, annee, mois, j), n)
                     for j, n in jours]
        if jour is not None:
            fil.append((libelle_jour(annee, mois, jour), url(filtres, annee, mois, jour)))

    medias = index.selectionner(filtres, annee, mois, jour)
    total = len(medias)
    pages = max(1, ceil(total / TAILLE_PAGE))
    page = min(max(1, page), pages)
    tranche = medias[(page - 1) * TAILLE_PAGE: page * TAILLE_PAGE]

    groupes: list[tuple[str, list[Media]]] = []
    if par_jour and blocs:
        for m in tranche:
            titre = libelle_jour(annee, mois, m.c.jour if m.c.jour is not None else SANS)
            if not groupes or groupes[-1][0] != titre:
                groupes.append((titre, []))
            groupes[-1][1].append(m)
    elif tranche:
        groupes = [("", tranche)]

    # Construire la position avant de retourner
    position = {k: str(v) for k, v in (("annee", annee), ("mois", mois), ("jour", jour)) if v is not None}

    return VueGalerie(
        fil[-1][0], fil, filtres, blocs, groupes, page, pages, total,
        precedente=url(filtres, annee, mois, jour, page - 1) if page > 1 else None,
        suivante=url(filtres, annee, mois, jour, page + 1) if page < pages else None,
        message=message, position=position)
