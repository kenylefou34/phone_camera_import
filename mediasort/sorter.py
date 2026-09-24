"""Orchestration : parcourt une source, range chaque média en toute sûreté."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import classify, config, dates
from .hashing import copy_and_hash, file_hash, quick_signature

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
    # Extensions non gérées (ni photo ni vidéo) : ignorées mais comptées,
    # sinon impossible de savoir qu'on en a perdu (issue #27).
    ignored: int = 0
    photos: int = 0
    videos: int = 0
    whatsapp: int = 0
    bytes_sorted: int = 0
    by_source_date: dict = field(default_factory=dict)
    by_year_month: dict = field(default_factory=dict)
    # Les fichiers en échec, NOMMÉS. Un compteur ne suffit pas : ce qui reste
    # dans le dossier trié contient aussi les doublons et le bruit exclu, que
    # l'appelant a raison de détruire. Seule cette liste dit ce qu'il faut
    # sauver (issue #16). Chemin RELATIF au dossier trié.
    echecs: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """Bilan sérialisable (clés françaises pour l'API)."""
        return {
            "sorted": self.sorted, "duplicates": self.duplicates,
            "to_triage": self.to_triage, "skipped": self.skipped,
            "errors": self.errors, "ignores": self.ignored, "photos": self.photos,
            "videos": self.videos, "whatsapp": self.whatsapp,
            "octets_ranges": self.bytes_sorted,
            "par_source_date": self.by_source_date,
            "par_annee_mois": self.by_year_month,
            "echecs": self.echecs,
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


def _retirer_copie_douteuse(destination: Path) -> None:
    """Efface la copie qu'on vient d'écrire quand la vérification a échoué.

    Sans ça, un fichier corrompu resterait dans la bibliothèque sans être au
    catalogue. C'est sûr : _chemin_libre() garantit que ce chemin n'existait
    pas avant, on ne peut donc pas effacer un média déjà rangé.
    """
    try:
        destination.unlink()
    except OSError:
        log.error("Copie douteuse impossible à retirer : %s", destination)


def sort_folder(source: Path, library: Path, catalog, dry_run: bool = True,
                 sur_mouvement=None) -> Report:
    """Range tous les médias de 'source' dans 'library'. Renvoie un Report détaillé.

    'sur_mouvement', si fourni, est appelé pour CHAQUE fichier rencontré avec
    le détail de son sort (issue #30) : rien n'est gardé en mémoire côté
    Report, c'est au consommateur de faire ce qu'il veut de chaque appel.
    """
    report = Report()

    def noter(p: Path, issue: str, empreinte=None, destination=None, detail=None):
        """Transmet le sort d'un fichier au consommateur, s'il y en a un.

        Rien n'est retenu ici : sur un tri de 20 000 médias en ligne de
        commande, garder la liste jusqu'à la fin coûterait pour rien.
        """
        if sur_mouvement is None:
            return
        try:
            taille = p.stat().st_size
        except OSError:
            taille = None
        sur_mouvement({"origine": p.relative_to(source).as_posix(), "taille": taille,
                       "empreinte": empreinte,
                       "destination": str(destination) if destination else None,
                       "issue": issue, "detail": detail})

    def echec(p: Path, raison: str) -> None:
        """Compte l'erreur ET retient le fichier, pour que l'appelant le sauve."""
        report.errors += 1
        report.echecs.append({"fichier": p.relative_to(source).as_posix(),
                              "raison": raison})
        noter(p, "erreur", detail=raison)

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
            report.ignored += 1  # ni photo ni vidéo : désormais compté (issue #27)
            noter(p, "refuse", detail="extension non gérée")
            continue
        if classify.is_excluded(p):
            report.skipped += 1
            noter(p, "exclu")
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
                    noter(p, "doublon", empreinte, catalog.chemin_de(empreinte))
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
                noter(p, "range" if dr.date else "a_trier", empreinte, dest)
                continue

            dest = _chemin_libre(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Copie en UNE seule lecture de la source : l'empreinte est calculée
            # au vol pendant l'écriture (issue #14). Elle sert de clé au
            # catalogue ET de référence pour vérifier la copie.
            empreinte_copiee = copy_and_hash(p, dest)
            if empreinte is not None and empreinte_copiee != empreinte:
                # L'empreinte du contrôle anti-doublon et celle lue à la copie
                # diffèrent : la source a changé entre-temps, on ne touche à rien.
                echec(p, "la source a changé pendant le tri")
                log.error("La source a changé pendant le tri : %s", p)
                _retirer_copie_douteuse(dest)
                continue
            # Copie sûre : on relit la destination avant de retirer la source.
            if file_hash(dest) != empreinte_copiee:
                echec(p, "empreinte différente après copie")
                log.error("Empreinte différente après copie : %s", dest)
                _retirer_copie_douteuse(dest)
                continue
            catalog.add_media(empreinte_copiee, p.stat().st_size, str(dest),
                              dr.date.isoformat() if dr.date else None, dr.source,
                              signature)
            noter(p, "range" if dr.date else "a_trier", empreinte_copiee, dest)
            p.unlink()
        except OSError as e:
            echec(p, str(e))
            log.error("Erreur sur %s : %s", p, e)
    return report
