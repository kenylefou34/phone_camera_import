"""Catalogue SQLite : anti-doublon par empreinte + dates de synchro par dossier."""

import sqlite3
from pathlib import Path

from . import config
from .hashing import file_hash

_MEDIA_EXTS = config.PHOTO_EXTS | config.VIDEO_EXTS


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

    def seed_from_library(self, library: Path) -> int:
        """Indexe tous les médias déjà présents en bibliothèque. Renvoie le nombre ajouté."""
        ajoutes = 0
        for p in library.rglob("*"):
            if p.is_file() and p.suffix.lower() in _MEDIA_EXTS:
                digest = file_hash(p)
                if not self.has_hash(digest):
                    self.add_media(digest, p.stat().st_size, str(p), None, "seed")
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
