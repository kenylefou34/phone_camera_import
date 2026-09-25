"""Le grand recensement de la galerie (spec §4) : vignettes + dates.

Une passe sur tout le catalogue qui, pour chaque média, fabrique sa vignette
et, si le catalogue ne connaît pas sa date de prise de vue, la récolte dans
les métadonnées (ou, à défaut, dans le nom du fichier). Les deux dans la même
passe : le coût est d'ouvrir le fichier, pas de le traiter.

Tourne dans son PROPRE processus (`phototheque-recensement.service`, `nice`
19, E/S au repos — ce qui ne vaut que pour ce processus : les lectures sur
Famille passent par le démon ntfs-3g, qui n'en hérite pas), jamais dans une
requête web :
- reprenable : la table `vignettes` dit ce qui est fait ; un média n'y est
  marqué « faite » qu'APRÈS l'écriture de sa date (voir `Passe.executer`) ;
- discret : il s'efface quand une synchronisation du téléphone est en cours
  (vérifié entre deux médias) — c'est LA protection de la synchro ; il se met
  aussi en pause si la bibliothèque a disparu (disque démonté) ;
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
import os
import signal
import sqlite3
import time
from dataclasses import dataclass
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


@dataclass
class _Resultat:
    """Ce qu'un média a donné, pas encore enregistré (voir Passe._enregistrer)."""
    media: Media
    vignette: tuple[int, int, str] | None = None   # (largeur, hauteur, méthode)
    erreur: str | None = None                      # échec de la vignette
    date: tuple[str, str, str] | None = None       # (empreinte, jour, source)


def _nombre(n: int) -> str:
    """44120 -> « 44 120 », comme sur les pages web."""
    return f"{n:,}".replace(",", " ")


class Passe:
    def __init__(self, catalog_db, vignettes: Vignettes, dossier: Path, bibliotheque: Path,
                 incoming: Path, lire=fabrique.lire_metadonnees,
                 fabriquer=fabrique.fabriquer_vignette, dormir=time.sleep,
                 doit_s_arreter=lambda: False):
        self.catalog_db, self.vignettes, self.dossier = catalog_db, vignettes, dossier
        self.bibliotheque, self.incoming = Path(bibliotheque), incoming
        self.lire, self.fabriquer = lire, fabriquer
        self.dormir, self.doit_s_arreter = dormir, doit_s_arreter

    # --- quand travailler -------------------------------------------------

    def _bibliotheque_montee(self) -> bool:
        """Faux si la bibliothèque n'est plus là (disque Famille démonté ou
        débranché). Un point de montage resté en place mais VIDE compte comme
        démonté : une bibliothèque réellement vide n'a de toute façon rien à
        recenser. Sans ce contrôle, chaque média serait marqué « fichier
        absent » — et ne serait plus jamais retenté sans --reessayer-erreurs."""
        try:
            with os.scandir(self.bibliotheque) as entrees:
                return next(entrees, None) is not None
        except OSError:
            return False

    def _raison_de_pause(self) -> str | None:
        if not self._bibliotheque_montee():
            return f"bibliothèque introuvable ({self.bibliotheque}) : disque démonté ?"
        if synchro_en_cours(self.incoming):
            return "synchronisation du téléphone en cours"
        return None

    def _attendre_le_feu_vert(self) -> bool:
        """Attend que rien n'empêche de travailler. Faux si un arrêt est
        demandé entre-temps (vérifié avant CHAQUE attente)."""
        annonce = False
        while True:
            if self.doit_s_arreter():
                return False
            raison = self._raison_de_pause()
            if raison is None:
                if annonce:
                    _log.info("reprise du recensement")
                return True
            if not annonce:
                _log.info("recensement en pause : %s", raison)
                annonce = True
            self.dormir(PAUSE_SYNCHRO_S)

    # --- la passe ---------------------------------------------------------

    def executer(self, limite: int | None = None) -> dict:
        """Une passe sur ce qui reste à faire.

        Ordre des écritures, pour qu'un arrêt BRUTAL (SIGKILL de systemd,
        manque de mémoire, coupure de courant, redémarrage par install.sh) ne
        perde jamais rien : on fabrique les vignettes d'un lot en gardant les
        résultats en mémoire, puis on écrit les DATES du lot, puis seulement on
        enregistre « faite » / « erreur ». Un média « faite » a donc toujours
        sa date écrite ; tué en route, on ne perd que des vignettes à refaire
        (le fichier WebP est simplement réécrit, sans dommage).

        Entre deux médias, on regarde si un arrêt est demandé, si une
        synchronisation a commencé ou si la bibliothèque a disparu : dans ces
        cas, ce qui est déjà fabriqué est enregistré d'abord.
        """
        bilan = {"faites": 0, "erreurs": 0, "dates": 0}
        restants = a_traiter(self.catalog_db, self.vignettes, self.bibliotheque)
        if limite is not None:
            restants = restants[:limite]
        traites = 0
        for debut in range(0, len(restants), LOT):
            if not self._attendre_le_feu_vert():
                return bilan
            lot = restants[debut:debut + LOT]
            avant = dict(bilan)
            metas = self._lire_metadonnees(lot)
            en_attente: list[_Resultat] = []
            vus = 0
            for m in lot:
                if en_attente and (self.doit_s_arreter() or self._raison_de_pause()):
                    self._enregistrer(en_attente, bilan)
                    en_attente = []
                    if not self._attendre_le_feu_vert():
                        self._journaliser_lot(vus, avant, bilan, len(restants) - traites - vus)
                        return bilan
                en_attente.append(self._traiter(m, metas.get(m.chemin, {})))
                vus += 1
            self._enregistrer(en_attente, bilan)
            traites += vus
            self._journaliser_lot(vus, avant, bilan, len(restants) - traites)
        return bilan

    def _lire_metadonnees(self, lot: list[Media]) -> dict:
        presents = [m.chemin for m in lot if Path(m.chemin).is_file()]
        try:
            return self.lire(presents)
        except Exception:                          # exiftool en panne : on continue sans
            _log.exception("métadonnées illisibles pour un lot")
            return {}

    def _traiter(self, m: Media, meta: dict) -> _Resultat:
        """Fabrique la vignette et récolte la date d'UN média, sans rien
        enregistrer. Une erreur n'arrête jamais la passe."""
        res = _Resultat(m)
        present = Path(m.chemin).is_file()
        try:
            if not present:
                raise fabrique.ErreurVignette("fichier absent de la bibliothèque")
            res.vignette = self.fabriquer(
                m.chemin, m.c.type, meta, chemin_vignette(self.dossier, m.empreinte))
        except fabrique.ErreurVignette as e:       # échec prévu : ffmpeg, fichier absent…
            res.erreur = str(e)
            _log.warning("vignette impossible pour %s : %s", m.nom, e)
        except Exception as e:                     # bogue inattendu : trace complète
            res.erreur = str(e) or type(e).__name__
            _log.exception("erreur inattendue pour %s", m.nom)
        if m.c.source != "date_prise" and present:
            recolte = recolter_date(meta, m.nom)
            if recolte:
                res.date = (m.empreinte, *recolte)
        return res

    def _enregistrer(self, resultats: list[_Resultat], bilan: dict) -> None:
        """Écrit les dates, PUIS enregistre faite/erreur (voir `executer`)."""
        if not resultats:
            return
        dates = [r.date for r in resultats if r.date]
        ecrites, echec, interrompu = self._ecrire_dates_avec_reprises(dates)
        bilan["dates"] += ecrites
        for r in resultats:
            if r.erreur is not None:
                # Déjà en erreur pour sa vignette : --reessayer-erreurs le
                # reprendra entièrement (vignette + date).
                self.vignettes.enregistrer_erreur(r.media.empreinte, r.erreur)
                bilan["erreurs"] += 1
            elif r.date is not None and echec is not None:
                if interrompu:
                    # Arrêt demandé pendant les reprises : on n'enregistre
                    # RIEN pour ce média, il sera simplement refait (vignette
                    # et date) au prochain démarrage.
                    continue
                message = f"date non écrite : {echec}"
                self.vignettes.enregistrer_erreur(r.media.empreinte, message)
                bilan["erreurs"] += 1
                _log.warning("%s : %s", r.media.nom, message)
            else:
                self.vignettes.enregistrer_faite(r.media.empreinte, *r.vignette)
                bilan["faites"] += 1

    def _journaliser_lot(self, vus: int, avant: dict, bilan: dict, restants: int) -> None:
        """Une ligne par lot dans « journalctl -u phototheque-recensement »."""
        _log.info("lot : %s médias, %s vignettes, %s échecs, %s dates, %s restants",
                  _nombre(vus), _nombre(bilan["faites"] - avant["faites"]),
                  _nombre(bilan["erreurs"] - avant["erreurs"]),
                  _nombre(bilan["dates"] - avant["dates"]), _nombre(restants))

    def _ecrire_dates_avec_reprises(self, dates: list[tuple[str, str, str]]
                                    ) -> tuple[int, Exception | None, bool]:
        """Écrit les dates d'un lot, avec reprises devant un verrou transitoire.

        Renvoie (lignes écrites, dernière erreur ou None, arrêt demandé ?).

        Le catalogue (`~/mediasort_catalog.db`) est une base SQLite à journal
        de retour arrière (pas WAL) : elle est PARTAGÉE avec le trieur en
        ligne de commande et celui du service d'upload, qui peuvent la tenir
        verrouillée plus longtemps que les 30 s de `ecrire_dates`. Sans
        reprise, un simple `database is locked` ferait remonter jusqu'à
        `main()` et planter le processus du recensement.

        Après 3 tentatives infructueuses, l'appelant enregistre ces médias en
        ERREUR « date non écrite » au lieu de « faite » : sinon `a_traiter` ne
        les reproposerait plus jamais alors que leur date manque. Un arrêt
        demandé avant une attente l'écourte : on n'attend pas 30 s de plus.
        """
        derniere_erreur = None
        for tentative in range(3):
            try:
                return ecrire_dates(self.catalog_db, dates), None, False
            except sqlite3.Error as e:
                derniere_erreur = e
                if tentative < 2:
                    if self.doit_s_arreter():
                        return 0, e, True
                    self.dormir(PAUSE_SYNCHRO_S)
                else:
                    _log.exception("écriture des dates impossible pour un lot, après 3 tentatives")
        return 0, derniere_erreur, False


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

    def dormir(secondes: float) -> None:
        # Attente découpée en pas d'une seconde : un `systemctl stop` (SIGTERM)
        # pendant une pause de 30 s est entendu tout de suite, au lieu
        # d'attendre la fin de la pause.
        for _ in range(int(secondes)):
            if arret["demande"]:
                return
            time.sleep(1)

    passe = Passe(config.CATALOG_DB, vignettes, config.VIGNETTES_DIR, config.LIBRARY_DIR,
                  config.INCOMING_DIR, dormir=dormir, doit_s_arreter=lambda: arret["demande"])
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
