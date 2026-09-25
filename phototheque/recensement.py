"""Le grand recensement de la galerie (spec §4) : vignettes + dates.

Une passe sur tout le catalogue qui, pour chaque média, fabrique sa vignette
et, si le catalogue ne connaît pas sa date de prise de vue, la récolte dans
les métadonnées (ou, à défaut, dans le nom du fichier). Les deux dans la même
passe : le coût est d'ouvrir le fichier, pas de le traiter.

Tourne dans son PROPRE processus (`phototheque-recensement.service`, `nice`
19, E/S au repos), jamais dans une requête web :
- reprenable : la table `vignettes` dit ce qui est fait ;
- discret : il s'efface quand une synchronisation du téléphone est en cours ;
- unique : un verrou de fichier empêche deux exemplaires ;
- permanent : l'arriéré fini, il repasse toutes les 10 minutes pour les
  médias nouvellement importés.

Écritures : fichiers de vignettes (disque système), base de la galerie, et
`date_prise` du catalogue SEULEMENT quand elle est vide. Rien sous la
bibliothèque.
"""

import argparse
import fcntl
import logging
import signal
import sqlite3
import time
from pathlib import Path

from mediasort.dates import _pick_metadata_date, date_from_filename

from . import config, fabrique, sessions
from .galerie_index import Index, Media
from .vignettes import Vignettes, chemin_vignette

LOT = 50                     # fichiers par appel exiftool et par écriture de dates
PAUSE_SYNCHRO_S = 30         # attente entre deux vérifications pendant une synchro
INTERVALLE_S = 600           # repos entre deux passes, une fois l'arriéré fini

_log = logging.getLogger("phototheque.recensement")


def a_traiter(catalog_db: Path, vignettes: Vignettes, bibliotheque: Path) -> list[Media]:
    """Médias sans vignette ni erreur, le plus récent d'abord : ce sont les
    mois qu'on regarde en premier qui se remplissent en premier."""
    faits = vignettes.traitees()
    restants = [m for m in Index.depuis_catalogue(catalog_db, bibliotheque).tous()
                if m.empreinte not in faits]
    restants.sort(key=lambda m: (m.c.annee or 0, m.c.mois or 0, m.c.jour or 0, m.nom),
                  reverse=True)
    return restants


def synchro_en_cours(incoming: Path, fenetre_s: int = 300, maintenant=time.time) -> bool:
    """Vrai si une session de synchronisation a été écrite récemment.

    Le recensement tourne dans un autre processus que le serveur : il ne voit
    pas ses verrous. Il regarde donc le disque, comme la purge des sessions
    abandonnées : un dossier au nom de session (32 hexadécimaux — ce qui
    écarte la quarantaine `_echecs`) modifié il y a moins de `fenetre_s`.
    """
    try:
        dossiers = list(incoming.iterdir())
    except FileNotFoundError:
        return False
    for d in dossiers:
        if d.is_dir() and sessions.identifiant_valide(d.name):
            if maintenant() - sessions._mtime_le_plus_recent(d) < fenetre_s:
                return True
    return False


def recolter_date(meta: dict, nom: str) -> tuple[str, str] | None:
    """La date de prise de vue d'un média, ou None. Jamais la date système du
    fichier : sur une bibliothèque copiée, elle ne dit que la date de la copie."""
    d = _pick_metadata_date(meta) if meta else None
    if d is not None and d.year >= 1900:
        return d.isoformat(), "metadata"
    d = date_from_filename(nom)
    if d is not None:
        return d.isoformat(), "filename"
    return None


def ecrire_dates(catalog_db: Path, dates: list[tuple[str, str, str]]) -> int:
    """Comble `date_prise` là où elle est vide, en une transaction courte (le
    trieur écrit dans le même fichier). Renvoie le nombre de lignes écrites."""
    if not dates:
        return 0
    cx = sqlite3.connect(str(catalog_db), timeout=30)
    try:
        with cx:
            n = 0
            for empreinte, jour, source in dates:
                n += cx.execute(
                    "UPDATE medias SET date_prise=?, source_date=?"
                    " WHERE empreinte=? AND date_prise IS NULL",
                    (jour, source, empreinte)).rowcount
        return n
    finally:
        cx.close()


class Passe:
    def __init__(self, catalog_db, vignettes: Vignettes, dossier: Path, bibliotheque: Path,
                 incoming: Path, lire=fabrique.lire_metadonnees,
                 fabriquer=fabrique.fabriquer_vignette, dormir=time.sleep,
                 doit_s_arreter=lambda: False):
        self.catalog_db, self.vignettes, self.dossier = catalog_db, vignettes, dossier
        self.bibliotheque, self.incoming = bibliotheque, incoming
        self.lire, self.fabriquer = lire, fabriquer
        self.dormir, self.doit_s_arreter = dormir, doit_s_arreter

    def executer(self, limite: int | None = None) -> dict:
        bilan = {"faites": 0, "erreurs": 0, "dates": 0}
        restants = a_traiter(self.catalog_db, self.vignettes, self.bibliotheque)
        if limite is not None:
            restants = restants[:limite]
        for debut in range(0, len(restants), LOT):
            while synchro_en_cours(self.incoming):
                if self.doit_s_arreter():
                    return bilan
                self.dormir(PAUSE_SYNCHRO_S)
            if self.doit_s_arreter():
                return bilan
            lot = restants[debut:debut + LOT]
            presents = [m for m in lot if Path(m.chemin).is_file()]
            try:
                metas = self.lire([m.chemin for m in presents])
            except Exception:                      # exiftool en panne : on continue sans
                _log.exception("métadonnées illisibles pour un lot")
                metas = {}
            dates = []
            for m in lot:
                meta = metas.get(m.chemin, {})
                try:
                    if m not in presents:
                        raise fabrique.ErreurVignette("fichier absent de la bibliothèque")
                    largeur, hauteur, methode = self.fabriquer(
                        m.chemin, m.c.type, meta, chemin_vignette(self.dossier, m.empreinte))
                    self.vignettes.enregistrer_faite(m.empreinte, largeur, hauteur, methode)
                    bilan["faites"] += 1
                except Exception as e:             # une erreur n'arrête jamais la passe
                    self.vignettes.enregistrer_erreur(m.empreinte, str(e))
                    bilan["erreurs"] += 1
                if m.c.source != "date_prise" and m in presents:
                    recolte = recolter_date(meta, m.nom)
                    if recolte:
                        dates.append((m.empreinte, *recolte))
            bilan["dates"] += ecrire_dates(self.catalog_db, dates)
        return bilan


def _prendre_verrou(chemin: Path):
    """Verrou exclusif non bloquant ; None si un autre recensement tourne."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    f = open(chemin, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Recensement de la galerie : vignettes et dates.")
    parser.add_argument("--une-passe", action="store_true", help="une seule passe, puis s'arrêter")
    parser.add_argument("--limite", type=int, default=None, help="au plus N médias")
    parser.add_argument("--reessayer-erreurs", action="store_true",
                        help="remettre en file les médias en échec")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    verrou = _prendre_verrou(config.DATA_DIR / "recensement.verrou")
    if verrou is None:
        _log.info("un autre recensement tourne déjà : rien à faire")
        return 0

    arret = {"demande": False}
    signal.signal(signal.SIGTERM, lambda *_: arret.update(demande=True))
    vignettes = Vignettes(config.GALERIE_DB)
    if args.reessayer_erreurs:
        _log.info("%d média(s) en échec remis en file", vignettes.oublier_erreurs())
    passe = Passe(config.CATALOG_DB, vignettes, config.VIGNETTES_DIR, config.LIBRARY_DIR,
                  config.INCOMING_DIR, doit_s_arreter=lambda: arret["demande"])
    while True:
        debut = time.monotonic()
        bilan = passe.executer(limite=args.limite)
        _log.info("passe terminée en %.0f s : %d vignette(s), %d échec(s), %d date(s)",
                  time.monotonic() - debut, bilan["faites"], bilan["erreurs"], bilan["dates"])
        if args.une_passe or arret["demande"]:
            return 0
        for _ in range(INTERVALLE_S):              # repos, interruptible chaque seconde
            if arret["demande"]:
                return 0
            time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
