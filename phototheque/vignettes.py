"""Table des vignettes de la galerie : ce qui est fait, ce qui a échoué.

C'est elle qui rend le recensement REPRENABLE : une vignette faite ou en
échec n'est plus retentée (sauf `oublier_erreurs`, à la demande). Base
distincte du catalogue (`config.GALERIE_DB`), en mode WAL : le serveur web la
lit pendant que le recensement, un autre processus, y écrit.
"""

import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

# Une empreinte SHA-256 en hexadécimal minuscule, et rien d'autre. C'est le
# seul identifiant qu'une requête de la galerie peut porter (spec §7).
EMPREINTE = re.compile(r"[0-9a-f]{64}")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vignettes (
  empreinte TEXT PRIMARY KEY,
  etat TEXT NOT NULL,              -- 'faite' ou 'erreur'
  largeur INTEGER, hauteur INTEGER,
  methode TEXT,                    -- 'exif', 'photo' ou 'video'
  erreur TEXT,
  faite_le TEXT NOT NULL);
"""


def _verifier(empreinte: str) -> str:
    if not EMPREINTE.fullmatch(empreinte):
        raise ValueError(f"empreinte non autorisée : {empreinte!r}")
    return empreinte


def chemin_vignette(dossier: Path, empreinte: str) -> Path:
    """`<dossier>/aa/aaaa….webp` : 256 sous-dossiers plutôt que 45 000
    fichiers dans un seul répertoire."""
    e = _verifier(empreinte)
    return dossier / e[:2] / f"{e}.webp"


def chemin_moyenne(dossier: Path, empreinte: str) -> Path:
    """La taille intermédiaire (1280 px), fabriquée à la première ouverture."""
    e = _verifier(empreinte)
    return dossier / "moyennes" / e[:2] / f"{e}.webp"


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Vignettes:
    def __init__(self, db_path) -> None:
        self._cx = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
        self._lock = threading.Lock()
        with self._lock:
            self._cx.execute("PRAGMA journal_mode=WAL")
            self._cx.executescript(_SCHEMA)
            self._cx.commit()

    def traitees(self) -> set[str]:
        with self._lock:
            return {r[0] for r in self._cx.execute("SELECT empreinte FROM vignettes")}

    def enregistrer_faite(self, empreinte: str, largeur: int, hauteur: int, methode: str) -> None:
        with self._lock:
            self._cx.execute(
                "INSERT OR REPLACE INTO vignettes VALUES (?, 'faite', ?, ?, ?, NULL, ?)",
                (empreinte, largeur, hauteur, methode, _maintenant()))
            self._cx.commit()

    def enregistrer_erreur(self, empreinte: str, erreur: str) -> None:
        with self._lock:
            self._cx.execute(
                "INSERT OR REPLACE INTO vignettes VALUES (?, 'erreur', NULL, NULL, NULL, ?, ?)",
                (empreinte, erreur[:500], _maintenant()))
            self._cx.commit()

    def oublier_erreurs(self) -> int:
        with self._lock:
            n = self._cx.execute("DELETE FROM vignettes WHERE etat='erreur'").rowcount
            self._cx.commit()
            return n

    def bilan(self) -> dict:
        with self._lock:
            faites, erreurs, derniere = self._cx.execute(
                "SELECT COALESCE(SUM(etat='faite'), 0), COALESCE(SUM(etat='erreur'), 0),"
                " MAX(faite_le) FROM vignettes").fetchone()
        return {"faites": faites, "erreurs": erreurs, "derniere": derniere}

    def dernieres_erreurs(self, n: int = 20) -> list[dict]:
        with self._lock:
            lignes = self._cx.execute(
                "SELECT empreinte, erreur, faite_le FROM vignettes WHERE etat='erreur'"
                " ORDER BY faite_le DESC LIMIT ?", (n,)).fetchall()
        return [{"empreinte": e, "erreur": err, "quand": q} for e, err, q in lignes]

    def close(self) -> None:
        with self._lock:
            self._cx.close()
