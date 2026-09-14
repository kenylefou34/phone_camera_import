"""Orchestration : parcourt une source, range chaque média en toute sûreté."""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import classify
from .dates import resolve_date
from .hashing import file_hash

log = logging.getLogger("mediasort")


@dataclass
class Report:
    """Compteurs du déroulement d'un tri."""
    listed: int = 0
    sorted: int = 0
    duplicates: int = 0
    to_triage: int = 0
    skipped: int = 0
    errors: int = 0


def _chemin_libre(destination: Path) -> Path:
    """Si le nom existe déjà (contenu différent), suffixe _1, _2, ..."""
    if not destination.exists():
        return destination
    tige, suffixe = destination.stem, destination.suffix
    n = 1
    while True:
        candidat = destination.with_name(f"{tige}_{n}{suffixe}")
        if not candidat.exists():
            return candidat
        n += 1


def sort_folder(source: Path, library: Path, catalog, dry_run: bool = True) -> Report:
    """Range tous les médias de 'source' dans 'library'. Renvoie un Report."""
    report = Report()
    for p in sorted(source.rglob("*")):
        if not p.is_file():
            continue
        mtype = classify.media_type(p.suffix)
        if mtype is None:
            continue  # ni photo ni vidéo : ignoré ici (le bruit est traité à part)
        if classify.is_excluded(p):
            report.skipped += 1
            continue
        report.listed += 1
        try:
            empreinte = file_hash(p)
            if catalog.has_hash(empreinte):
                report.duplicates += 1
                log.info("DOUBLON ignoré : %s", p)
                continue

            dr = resolve_date(p)
            dest = classify.destination(library, p, dr, mtype)
            if dr.date is None:
                report.to_triage += 1
            else:
                report.sorted += 1
            log.info("%s -> %s (date: %s)", p.name, dest, dr.source)

            if dry_run:
                continue

            dest = _chemin_libre(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
            # Copie sûre : on vérifie l'empreinte à destination avant de retirer la source.
            if file_hash(dest) != empreinte:
                report.errors += 1
                log.error("Empreinte différente après copie : %s", dest)
                continue
            catalog.add_media(empreinte, p.stat().st_size, str(dest),
                              dr.date.isoformat() if dr.date else None, dr.source)
            p.unlink()
        except OSError as e:
            report.errors += 1
            log.error("Erreur sur %s : %s", p, e)
    return report
