"""Catalogue SQLite : anti-doublon par empreinte + dates de synchro par dossier."""

import os
import sqlite3
from pathlib import Path

from . import config
from .hashing import file_hash

_MEDIA_EXTS = config.PHOTO_EXTS | config.VIDEO_EXTS
# Dossiers système à ne jamais parcourir lors de l'amorçage.
_SKIP_DIR_NAMES = {"System Volume Information", "$RECYCLE.BIN"}


class Catalog:
    """Mémoire persistante des médias déjà en bibliothèque."""

    def __init__(self, db_path) -> None:
        self._cx = sqlite3.connect(str(db_path))
        self._cx.execute(
            "CREATE TABLE IF NOT EXISTS medias ("
            " empreinte TEXT PRIMARY KEY, taille INTEGER, chemin TEXT,"
            " date_prise TEXT, source_date TEXT, date_import TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self._cx.execute(
            "CREATE TABLE IF NOT EXISTS synchros ("
            " dossier TEXT PRIMARY KEY, dernier_ts REAL)"
        )
        self._cx.commit()

    def has_hash(self, digest: str) -> bool:
        cur = self._cx.execute("SELECT 1 FROM medias WHERE empreinte=?", (digest,))
        return cur.fetchone() is not None

    def add_media(self, digest: str, size: int, path: str,
                  date_prise, source_date: str) -> None:
        # INSERT OR IGNORE : une empreinte n'est enregistrée qu'une fois.
        self._cx.execute(
            "INSERT OR IGNORE INTO medias"
            " (empreinte, taille, chemin, date_prise, source_date)"
            " VALUES (?,?,?,?,?)",
            (digest, size, path, date_prise, source_date),
        )
        self._cx.commit()

    def count(self) -> int:
        return self._cx.execute("SELECT COUNT(*) FROM medias").fetchone()[0]

    def seed_from_library(self, library, exclude=None) -> int:
        """Indexe les médias déjà rangés en bibliothèque (pour l'anti-doublon).

        Saute les dossiers de transit passés dans 'exclude' (ex. le dossier
        source à trier, '_A_TRIER'), ainsi que les dossiers cachés et système.
        Tolère les fichiers illisibles. Renvoie le nombre de médias ajoutés.
        """
        exclus = {os.path.abspath(str(e)) for e in (exclude or [])}
        ajoutes = 0
        for racine, dossiers, fichiers in os.walk(str(library), onerror=lambda e: None):
            # Élaguer : dossiers cachés, système et exclus (on n'y descend pas).
            dossiers[:] = [
                d for d in dossiers
                if not d.startswith((".", "$"))
                and d not in _SKIP_DIR_NAMES
                and os.path.abspath(os.path.join(racine, d)) not in exclus
            ]
            for nom in fichiers:
                p = Path(racine) / nom
                if p.suffix.lower() not in _MEDIA_EXTS:
                    continue
                try:
                    digest = file_hash(p)
                    taille = p.stat().st_size
                except OSError:
                    continue
                if not self.has_hash(digest):
                    self.add_media(digest, taille, str(p), None, "seed")
                    ajoutes += 1
        return ajoutes

    def get_last_sync(self, folder: str):
        cur = self._cx.execute("SELECT dernier_ts FROM synchros WHERE dossier=?", (folder,))
        ligne = cur.fetchone()
        return ligne[0] if ligne else None

    def set_last_sync(self, folder: str, ts: float) -> None:
        self._cx.execute(
            "INSERT INTO synchros (dossier, dernier_ts) VALUES (?,?)"
            " ON CONFLICT(dossier) DO UPDATE SET dernier_ts=excluded.dernier_ts",
            (folder, ts),
        )
        self._cx.commit()

    def close(self) -> None:
        self._cx.close()
