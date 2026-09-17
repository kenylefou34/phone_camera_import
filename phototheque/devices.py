"""Stockage et validation des jetons d'appareils appairés (SQLite, thread-safe)."""

import hashlib
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class DeviceStore:
    """Un appareil appairé = un secret (stocké haché) + un label.

    La connexion est partagée entre les threads de requête du serveur, d'où
    check_same_thread=False + un verrou qui sérialise les accès.
    """

    def __init__(self, db_path) -> None:
        self._cx = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._cx.execute(
                "CREATE TABLE IF NOT EXISTS devices ("
                " id TEXT PRIMARY KEY, label TEXT, secret_hash TEXT UNIQUE, paired_at TEXT)"
            )
            self._cx.commit()

    def pair(self, label: str) -> tuple:
        """Crée un appareil, renvoie (id, secret en clair) — le secret n'est montré qu'ici."""
        dev_id = uuid.uuid4().hex
        secret = secrets.token_urlsafe(32)
        with self._lock:
            self._cx.execute(
                "INSERT INTO devices (id, label, secret_hash, paired_at) VALUES (?,?,?,?)",
                (dev_id, label, _hash(secret), datetime.now().isoformat(timespec="seconds")),
            )
            self._cx.commit()
        return dev_id, secret

    def validate(self, secret: str):
        with self._lock:
            cur = self._cx.execute("SELECT id FROM devices WHERE secret_hash=?", (_hash(secret),))
            row = cur.fetchone()
        return row[0] if row else None

    def list(self) -> list:
        with self._lock:
            cur = self._cx.execute("SELECT id, label, paired_at FROM devices ORDER BY paired_at")
            rows = cur.fetchall()
        return [{"id": i, "label": l, "paired_at": p} for (i, l, p) in rows]

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            cur = self._cx.execute("DELETE FROM devices WHERE id=?", (device_id,))
            self._cx.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._cx.close()
