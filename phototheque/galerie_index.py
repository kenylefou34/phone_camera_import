"""Index en mémoire des médias du catalogue, pour la galerie (lecture seule).

Une seule requête SQL lit tout le catalogue (45 643 lignes au 25/09, quelques
Mo en mémoire) ; les filtres, les comptes par année/mois/jour et la sélection
d'une grille se font ensuite en Python. Pourquoi pas en SQL ? Parce que
l'année et le mois se déduisent souvent du chemin (voir classement.py), ce
que SQLite ne sait pas faire proprement.

L'index est gardé en cache et reconstruit quand le fichier du catalogue
change — au plus toutes les RAFRAICHISSEMENT_MIN_S secondes, car le
recensement y écrit des dates par petits lots toute la nuit.
"""

import os
import sqlite3
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path, PurePosixPath

from .classement import Classement, classer
from .vignettes import EMPREINTE

# Valeur « inconnu » dans une sélection : le rayon « Sans date », le « Mois
# inconnu » d'une année, le « Jour inconnu » d'un mois.
SANS = "sans"

RAFRAICHISSEMENT_MIN_S = 30


@dataclass(frozen=True, slots=True)
class Media:
    empreinte: str
    chemin: str
    taille: int
    c: Classement

    @property
    def nom(self) -> str:
        return PurePosixPath(self.chemin).name


@dataclass(frozen=True)
class Filtres:
    du: date | None = None
    au: date | None = None
    type: str | None = None       # "photo" ou "video"
    origine: str | None = None    # "appareil", "whatsapp" ou "autre"


def _fin_du_mois(annee: int, mois: int) -> date:
    return date(annee + (mois == 12), mois % 12 + 1, 1) - timedelta(days=1)


def _dans_intervalle(c: Classement, du: date | None, au: date | None) -> bool:
    """Vrai si la période connue du média chevauche [du, au].

    Un média dont seul le mois (ou l'année) est connu est gardé dès que ce
    mois chevauche l'intervalle : mieux vaut le montrer en trop que le cacher.
    Un média sans aucune date est écarté dès qu'un filtre de dates est posé :
    on ne peut pas le placer.
    """
    if du is None and au is None:
        return True
    if c.annee is None:
        return False
    if c.mois is None:
        debut, fin = date(c.annee, 1, 1), date(c.annee, 12, 31)
    else:
        debut, fin = date(c.annee, c.mois, 1), _fin_du_mois(c.annee, c.mois)
        if c.jour is not None:
            try:
                debut = fin = date(c.annee, c.mois, c.jour)
            except ValueError:
                pass      # « 30 février » venu d'un appareil déréglé : on garde le mois
    return (du is None or fin >= du) and (au is None or debut <= au)


def _ordonner(compte: Counter, decroissant: bool) -> list[tuple[int | str, int]]:
    """Clés connues triées, puis la case « inconnu » (SANS) en dernier."""
    connues = sorted((k for k in compte if k is not None), reverse=decroissant)
    resultat: list[tuple[int | str, int]] = [(k, compte[k]) for k in connues]
    if None in compte:
        resultat.append((SANS, compte[None]))
    return resultat


def _garde(valeur: int | None, voulu: int | str | None) -> bool:
    """`voulu` : None = pas de contrainte, SANS = inconnu, sinon égalité."""
    if voulu is None:
        return True
    if voulu == SANS:
        return valeur is None
    return valeur == voulu


class Index:
    def __init__(self, medias: list[Media]):
        self._medias = medias
        self._par_empreinte = {m.empreinte: m for m in medias}

    @classmethod
    def depuis_catalogue(cls, catalog_db: Path, bibliotheque: Path | str) -> "Index":
        # Lecture seule explicite (`mode=ro`) : la galerie n'écrit jamais ici.
        cx = sqlite3.connect(f"file:{catalog_db}?mode=ro", uri=True, timeout=30)
        try:
            lignes = cx.execute(
                "SELECT empreinte, chemin, taille, date_prise FROM medias"
                " WHERE chemin IS NOT NULL").fetchall()
        finally:
            cx.close()
        medias = []
        for empreinte, chemin, taille, date_prise in lignes:
            # Défense en profondeur : l'empreinte finit dans des href et des
            # src (spec §7). Le trieur n'écrit que des SHA-256 hexadécimaux,
            # mais une ligne abîmée ou forgée n'a rien à faire dans une page.
            if not isinstance(empreinte, str) or not EMPREINTE.fullmatch(empreinte):
                continue
            c = classer(chemin, date_prise, str(bibliotheque))
            if c is not None:
                medias.append(Media(empreinte, chemin, taille or 0, c))
        return cls(medias)

    def __len__(self) -> int:
        return len(self._medias)

    def tous(self) -> list[Media]:
        return list(self._medias)

    def trouver(self, empreinte: str) -> Media | None:
        return self._par_empreinte.get(empreinte)

    def filtrer(self, f: Filtres) -> list[Media]:
        return [m for m in self._medias
                if (f.type is None or m.c.type == f.type)
                and (f.origine is None or m.c.origine == f.origine)
                and _dans_intervalle(m.c, f.du, f.au)]

    def compter_annees(self, f: Filtres) -> list[tuple[int | str, int]]:
        return _ordonner(Counter(m.c.annee for m in self.filtrer(f)), decroissant=True)

    def compter_mois(self, f: Filtres, annee: int) -> list[tuple[int | str, int]]:
        return _ordonner(Counter(m.c.mois for m in self.filtrer(f) if m.c.annee == annee),
                         decroissant=True)

    def compter_jours(self, f: Filtres, annee: int, mois: int) -> list[tuple[int | str, int]]:
        return _ordonner(Counter(m.c.jour for m in self.filtrer(f)
                                 if m.c.annee == annee and m.c.mois == mois),
                         decroissant=False)

    def selectionner(self, f: Filtres, annee: int | str | None,
                     mois: int | str | None = None,
                     jour: int | str | None = None) -> list[Media]:
        """Les médias d'une case, jour connu d'abord puis par nom de fichier
        (qui porte le plus souvent l'heure : IMG_20230625_101500.jpg)."""
        choisis = [m for m in self.filtrer(f)
                   if _garde(m.c.annee, annee) and _garde(m.c.mois, mois)
                   and _garde(m.c.jour, jour)]
        choisis.sort(key=lambda m: (m.c.jour is None, m.c.jour or 0, m.nom))
        return choisis


_cache: dict = {"cle": None, "mtime": None, "index": None, "construit": 0.0}
_verrou = threading.Lock()


def vider_cache() -> None:
    """Pour les tests : oublie l'index gardé en mémoire."""
    with _verrou:
        _cache.update(cle=None, mtime=None, index=None, construit=0.0)


def index_courant(catalog_db: Path, bibliotheque: Path | str,
                  maintenant=time.monotonic) -> Index:
    """L'index du moment, reconstruit si le catalogue a changé (au plus
    toutes les RAFRAICHISSEMENT_MIN_S secondes)."""
    try:
        mtime = os.stat(catalog_db).st_mtime_ns
    except FileNotFoundError:
        return Index([])
    cle = (str(catalog_db), str(bibliotheque))
    with _verrou:
        perime = (_cache["index"] is None or _cache["cle"] != cle
                  or (_cache["mtime"] != mtime
                      and maintenant() - _cache["construit"] >= RAFRAICHISSEMENT_MIN_S))
        if perime:
            _cache.update(cle=cle, mtime=mtime, construit=maintenant(),
                          index=Index.depuis_catalogue(catalog_db, bibliotheque))
        return _cache["index"]
