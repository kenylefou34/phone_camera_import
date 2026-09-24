"""Stockage et validation des jetons d'appareils appairés (SQLite, thread-safe)."""

import hashlib
import secrets
import sqlite3
import threading
import uuid
from datetime import date, datetime, timedelta

# Durée de validité d'un appairage non utilisé. Chaque affichage de /pair crée
# un secret ; sans expiration, un QR affiché puis oublié resterait une clé
# d'accès valable indéfiniment.
DELAI_APPAIRAGE_MINUTES = 10


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _trop_vieux(horodatage: str, delai_minutes: int) -> bool:
    """Vrai si l'horodatage dépasse le délai. Une date illisible est périmée."""
    try:
        quand = datetime.fromisoformat(horodatage)
    except (TypeError, ValueError):
        return True
    return datetime.now() - quand > timedelta(minutes=delai_minutes)


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
                " id TEXT PRIMARY KEY, label TEXT, secret_hash TEXT UNIQUE,"
                " paired_at TEXT, confirmed_at TEXT)"
            )
            self._cx.execute(
                "CREATE TABLE IF NOT EXISTS horizons ("
                " appareil TEXT NOT NULL, dossier TEXT NOT NULL,"
                " dernier_ts REAL NOT NULL, PRIMARY KEY (appareil, dossier))"
            )
            self._migrer()
            self._cx.commit()

    def _migrer(self) -> None:
        """Ajoute les colonnes apparues après la création de la table.

        Les appareils déjà enregistrés sont considérés CONFIRMÉS : il est hors
        de question de déconnecter un téléphone qui fonctionne parce que le
        schéma a changé. Leur horizon initial reste NULL, c'est-à-dire aucune
        limite — on ne restreint pas rétroactivement ce qu'ils avaient le droit
        d'envoyer.
        """
        colonnes = {c[1] for c in self._cx.execute("PRAGMA table_info(devices)")}
        if "confirmed_at" not in colonnes:
            self._cx.execute("ALTER TABLE devices ADD COLUMN confirmed_at TEXT")
            self._cx.execute("UPDATE devices SET confirmed_at = paired_at")
        if "horizon_initial" not in colonnes:
            self._cx.execute("ALTER TABLE devices ADD COLUMN horizon_initial TEXT")

    def pair(self, label: str) -> tuple:
        """Crée un appairage EN ATTENTE, renvoie (id, secret en clair).

        Le secret n'est montré qu'ici. L'appareil ne devient définitif qu'au
        premier usage réel du jeton (voir validate) ; d'ici là il expire.

        L'horizon initial est posé ICI, à la DATE DU JOUR, et non pas
        seulement quand l'administrateur valide le formulaire de /pair : dans
        le cas le plus courant (afficher le QR, scanner, c'est tout) personne
        ne touche au formulaire, et l'appareil se retrouvait avec NULL —
        c'est-à-dire « aucune limite ». Le téléphone remontait alors tout son
        historique, exactement ce que l'horizon de synchro devait éviter.

        NULL garde ainsi un seul sens : « appareil repris par _migrer(), ne
        pas restreindre rétroactivement ». Le formulaire, lui, remplace
        simplement cette date (voir set_horizon_initial).
        """
        dev_id = uuid.uuid4().hex
        secret = secrets.token_urlsafe(32)
        with self._lock:
            self._cx.execute(
                "INSERT INTO devices (id, label, secret_hash, paired_at,"
                " confirmed_at, horizon_initial) VALUES (?,?,?,?,NULL,?)",
                (dev_id, label, _hash(secret),
                 datetime.now().isoformat(timespec="seconds"),
                 date.today().isoformat()),
            )
            self._cx.commit()
        return dev_id, secret

    def validate(self, secret: str, delai_minutes: int = DELAI_APPAIRAGE_MINUTES):
        """Renvoie l'id de l'appareil si le secret est valable, sinon None.

        Un appairage encore en attente est CONFIRMÉ par ce premier usage : il
        ne pourra plus expirer. Passé le délai sans avoir servi, il est refusé.
        """
        with self._lock:
            cur = self._cx.execute(
                "SELECT id, paired_at, confirmed_at FROM devices WHERE secret_hash=?",
                (_hash(secret),),
            )
            row = cur.fetchone()
            if row is None:
                return None
            dev_id, paired_at, confirmed_at = row
            if confirmed_at is not None:
                return dev_id                      # appareil en service
            if _trop_vieux(paired_at, delai_minutes):
                return None                        # QR affiché puis jamais scanné
            self._cx.execute(
                "UPDATE devices SET confirmed_at=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), dev_id),
            )
            self._cx.commit()
        return dev_id

    def purge_pending(self, delai_minutes: int = DELAI_APPAIRAGE_MINUTES) -> int:
        """Supprime les appairages en attente périmés. Renvoie le nombre retiré.

        Ne touche ni aux appareils confirmés, ni aux appairages récents.
        """
        with self._lock:
            lignes = self._cx.execute(
                "SELECT id, paired_at FROM devices WHERE confirmed_at IS NULL"
            ).fetchall()
            perimes = [(i,) for (i, paired_at) in lignes
                       if _trop_vieux(paired_at, delai_minutes)]
            if perimes:
                self._cx.executemany("DELETE FROM devices WHERE id=?", perimes)
                self._cx.commit()
        return len(perimes)

    def is_pending(self, device_id: str) -> bool:
        """Vrai si cet appairage existe encore et n'a jamais servi.

        Faux s'il a été confirmé par un téléphone, révoqué, ou purgé après
        expiration. Permet à /pair de réafficher son appairage en cours plutôt
        que d'en créer un nouveau à chaque visite.
        """
        with self._lock:
            cur = self._cx.execute(
                "SELECT 1 FROM devices WHERE id=? AND confirmed_at IS NULL", (device_id,)
            )
            return cur.fetchone() is not None

    def list(self) -> list:
        with self._lock:
            cur = self._cx.execute(
                "SELECT id, label, paired_at, confirmed_at FROM devices ORDER BY paired_at"
            )
            rows = cur.fetchall()
        return [{"id": i, "label": l, "paired_at": p, "en_attente": c is None}
                for (i, l, p, c) in rows]

    def revoke(self, device_id: str) -> bool:
        """Retire un appareil ET ses horizons.

        La table `horizons` n'a ni clé étrangère ni `ON DELETE CASCADE`, et
        `PRAGMA foreign_keys` n'est jamais activé — SQLite le laisse inactif par
        défaut. Sans cette seconde requête, chaque révocation laissait ses lignes
        orphelines pour toujours.
        """
        with self._lock:
            cur = self._cx.execute("DELETE FROM devices WHERE id=?", (device_id,))
            self._cx.execute("DELETE FROM horizons WHERE appareil=?", (device_id,))
            self._cx.commit()
        return cur.rowcount > 0

    def set_horizon_initial(self, device_id: str, date_iso: str) -> None:
        """Date à partir de laquelle cet appareil remonte ses médias.

        Choisie à l'appairage. Sert de repli pour les dossiers dont on ne
        connaît pas encore d'horizon.
        """
        with self._lock:
            self._cx.execute(
                "UPDATE devices SET horizon_initial=? WHERE id=?", (date_iso, device_id)
            )
            self._cx.commit()

    def get_horizon_initial(self, device_id: str):
        with self._lock:
            cur = self._cx.execute(
                "SELECT horizon_initial FROM devices WHERE id=?", (device_id,)
            )
            ligne = cur.fetchone()
        return ligne[0] if ligne else None

    def set_horizon(self, device_id: str, dossier: str, ts: float) -> None:
        """Enregistre jusqu'où ce dossier a été synchronisé pour cet appareil."""
        with self._lock:
            self._cx.execute(
                "INSERT INTO horizons (appareil, dossier, dernier_ts) VALUES (?,?,?)"
                " ON CONFLICT(appareil, dossier) DO UPDATE SET dernier_ts=excluded.dernier_ts",
                (device_id, dossier, ts),
            )
            self._cx.commit()

    def get_horizons(self, device_id: str) -> dict:
        """Les horizons connus de cet appareil, par dossier."""
        with self._lock:
            lignes = self._cx.execute(
                "SELECT dossier, dernier_ts FROM horizons WHERE appareil=?", (device_id,)
            ).fetchall()
        return {dossier: ts for dossier, ts in lignes}

    def label(self, device_id: str) -> str | None:
        """Le nom affiché de cet appareil, ou None s'il est inconnu (issue #30).

        Sert au journal, qui garde le label au moment du commit : un appareil
        révoqué puis réappairé change d'identifiant, mais son nom reste lisible
        dans l'historique des synchros passées.
        """
        with self._lock:
            ligne = self._cx.execute(
                "SELECT label FROM devices WHERE id=?", (device_id,)
            ).fetchone()
        return ligne[0] if ligne else None

    def close(self) -> None:
        self._cx.close()
