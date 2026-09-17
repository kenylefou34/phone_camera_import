"""Orchestration : parcourt une source, range chaque média en toute sûreté."""

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import classify, config, dates
from .hashing import file_hash, quick_signature

log = logging.getLogger("mediasort")


@dataclass
class Report:
    """Compteurs du déroulement d'un tri (avec détail)."""
    listed: int = 0
    sorted: int = 0
    duplicates: int = 0
    to_triage: int = 0
    skipped: int = 0
    errors: int = 0
    photos: int = 0
    videos: int = 0
    whatsapp: int = 0
    bytes_sorted: int = 0
    by_source_date: dict = field(default_factory=dict)
    by_year_month: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Bilan sérialisable (clés françaises pour l'API)."""
        return {
            "sorted": self.sorted, "duplicates": self.duplicates,
            "to_triage": self.to_triage, "skipped": self.skipped,
            "errors": self.errors, "photos": self.photos,
            "videos": self.videos, "whatsapp": self.whatsapp,
            "octets_ranges": self.bytes_sorted,
            "par_source_date": self.by_source_date,
            "par_annee_mois": self.by_year_month,
        }


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
    """Range tous les médias de 'source' dans 'library'. Renvoie un Report détaillé."""
    report = Report()
    fichiers = [p for p in sorted(source.rglob("*")) if p.is_file()]
    # Pré-chargement des dates de métadonnées en un seul appel exiftool (perf).
    medias = [p for p in fichiers if classify.media_type(p.suffix) is not None]
    dates.prefetch_metadata(medias)
    # Pré-filtre par signature rapide (issue #9) : n'est SÛR que si toutes les
    # lignes du catalogue ont une signature ; sinon un doublon ancien passerait
    # au travers et serait copié en double. On l'évalue une fois pour tout le tri.
    prefiltre = catalog.signatures_complete()
    for p in fichiers:
        mtype = classify.media_type(p.suffix)
        if mtype is None:
            continue  # ni photo ni vidéo : ignoré ici (le bruit est traité à part)
        if classify.is_excluded(p):
            report.skipped += 1
            continue
        report.listed += 1
        try:
            # Signature rapide : ne lit que le début et la fin du fichier.
            signature = quick_signature(p)
            if prefiltre and not catalog.has_signature(signature):
                # Signature inconnue => contenu forcément nouveau : on s'épargne
                # la lecture intégrale (décisif sur les grosses vidéos).
                empreinte = None
            else:
                # Signature déjà vue (ou pré-filtre désactivé) : seule l'empreinte
                # complète prouve qu'il s'agit vraiment du même fichier.
                empreinte = file_hash(p)
                if catalog.has_hash(empreinte):
                    report.duplicates += 1
                    log.info("DOUBLON ignoré : %s", p)
                    continue

            dr = dates.resolve_date(p)
            dest = classify.destination(library, p, dr, mtype)
            if dr.date is None:
                report.to_triage += 1
            else:
                report.sorted += 1

            # --- détail du bilan (compté aussi en simulation) ---
            if mtype == "photo":
                report.photos += 1
            elif mtype == "video":
                report.videos += 1
            if classify.is_whatsapp(p):
                report.whatsapp += 1
            report.by_source_date[dr.source] = report.by_source_date.get(dr.source, 0) + 1
            if dr.date is not None:
                cle = f"{dr.date.year:04d}/{config.month_folder(dr.date.month)}"
                report.by_year_month[cle] = report.by_year_month.get(cle, 0) + 1
            try:
                report.bytes_sorted += p.stat().st_size
            except OSError:
                pass

            log.info("%s -> %s (date: %s)", p.name, dest, dr.source)
            if dry_run:
                continue

            dest = _chemin_libre(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Le rangement réel exige l'empreinte complète : elle sert de clé au
            # catalogue ET de référence pour vérifier la copie.
            if empreinte is None:
                empreinte = file_hash(p)
            shutil.copy2(p, dest)
            # Copie sûre : on vérifie l'empreinte à destination avant de retirer la source.
            if file_hash(dest) != empreinte:
                report.errors += 1
                log.error("Empreinte différente après copie : %s", dest)
                continue
            catalog.add_media(empreinte, p.stat().st_size, str(dest),
                              dr.date.isoformat() if dr.date else None, dr.source,
                              signature)
            p.unlink()
        except OSError as e:
            report.errors += 1
            log.error("Erreur sur %s : %s", p, e)
    return report
