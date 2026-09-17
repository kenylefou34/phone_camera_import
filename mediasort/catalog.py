"""Catalogue SQLite : anti-doublon par empreinte de contenu."""

import os
import sqlite3
from pathlib import Path

from . import config
from .hashing import file_hash, quick_signature

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
        self._migrer_signature()
        self._cx.commit()

    def _migrer_signature(self) -> None:
        """Ajoute la colonne 'signature' aux catalogues créés avant elle.

        Les lignes déjà présentes gardent une signature NULL : c'est ce que
        signatures_complete() détecte pour désactiver le pré-filtre.
        """
        colonnes = {c[1] for c in self._cx.execute("PRAGMA table_info(medias)")}
        if "signature" not in colonnes:
            self._cx.execute("ALTER TABLE medias ADD COLUMN signature TEXT")
        self._cx.execute(
            "CREATE INDEX IF NOT EXISTS idx_medias_signature ON medias(signature)"
        )

    def has_hash(self, digest: str) -> bool:
        cur = self._cx.execute("SELECT 1 FROM medias WHERE empreinte=?", (digest,))
        return cur.fetchone() is not None

    def add_media(self, digest: str, size: int, path: str,
                  date_prise, source_date: str, signature=None) -> None:
        # INSERT OR IGNORE : une empreinte n'est enregistrée qu'une fois.
        self._cx.execute(
            "INSERT OR IGNORE INTO medias"
            " (empreinte, taille, chemin, date_prise, source_date, signature)"
            " VALUES (?,?,?,?,?,?)",
            (digest, size, path, date_prise, source_date, signature),
        )
        self._cx.commit()

    def has_signature(self, signature: str) -> bool:
        """Vrai si une signature rapide identique est déjà connue.

        ATTENTION : une signature n'est PAS une preuve d'égalité (collisions
        possibles). Elle sert seulement de pré-filtre : « faux » prouve que le
        fichier est nouveau, « vrai » impose de vérifier l'empreinte complète.
        """
        cur = self._cx.execute(
            "SELECT 1 FROM medias WHERE signature=? LIMIT 1", (signature,)
        )
        return cur.fetchone() is not None

    def signatures_complete(self) -> bool:
        """Vrai si toutes les lignes ont une signature (pré-filtre utilisable).

        Si une seule ligne n'en a pas, un fichier identique à celle-ci passerait
        le pré-filtre sans être reconnu comme doublon : on désactive alors le
        raccourci et on hache tout, comme avant.
        """
        cur = self._cx.execute("SELECT 1 FROM medias WHERE signature IS NULL LIMIT 1")
        return cur.fetchone() is None

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
                    signature = quick_signature(p)
                    taille = p.stat().st_size
                except OSError:
                    continue
                if not self.has_hash(digest):
                    self.add_media(digest, taille, str(p), None, "seed", signature)
                    ajoutes += 1
        return ajoutes

    def backfill_signatures(self, lot: int = 200, progression=None) -> int:
        """Calcule les signatures manquantes des lignes déjà enregistrées.

        Sert à réactiver le pré-filtre sur un catalogue d'avant la colonne
        'signature' : on relit seulement le début et la fin de chaque fichier
        (pas tout le contenu). Les fichiers disparus ou illisibles sont laissés
        sans signature. Renvoie le nombre de lignes complétées.

        Le travail se fait par lots de 'lot' lignes, et chaque lot est d'abord
        calculé EN ENTIER (lectures disque, aucune transaction ouverte) avant
        d'être écrit d'un seul coup. C'est important : le traitement dure une
        heure sur un gros catalogue, et le service phototheque écrit dans le même
        fichier. Le verrou d'écriture SQLite n'est donc tenu que le temps des
        UPDATE (quelques millisecondes), pas pendant les lectures.

        Autre effet : une interruption (Ctrl-C, coupure) ne perd que le lot en
        cours. Relancer la commande reprend là où elle s'était arrêtée, puisque
        seules les lignes sans signature sont sélectionnées.

        'progression' est une fonction optionnelle appelée à chaque lot avec
        (lignes_traitees, total), pour afficher l'avancement.
        """
        lignes = self._cx.execute(
            "SELECT empreinte, chemin FROM medias WHERE signature IS NULL"
        ).fetchall()
        total = len(lignes)
        completees = 0
        for debut in range(0, total, lot):
            # 1) Lectures seules : on calcule tout le lot, verrou non pris.
            calculees = []
            for empreinte, chemin in lignes[debut:debut + lot]:
                if not chemin:
                    continue
                try:
                    calculees.append((quick_signature(Path(chemin)), empreinte))
                except OSError:
                    continue  # fichier déplacé ou illisible : on laisse NULL
            # 2) Écriture groupée : le verrou n'est tenu que sur ces lignes.
            if calculees:
                self._cx.executemany(
                    "UPDATE medias SET signature=? WHERE empreinte=?", calculees
                )
                self._cx.commit()
                completees += len(calculees)
            if progression is not None:
                progression(min(debut + lot, total), total)
        return completees

    def close(self) -> None:
        self._cx.close()
