"""Intégration du trieur : range une session reçue, un tri à la fois."""

import threading
from pathlib import Path

from mediasort.sorter import Report, sort_folder

_verrou = threading.Lock()


def bilan_vide() -> dict:
    """Bilan d'un tri à zéro fichier : tous les compteurs à zéro.

    Sert au cas de la session vide (rien n'a été envoyé). On réutilise le
    Report du trieur plutôt que de retaper un dictionnaire : ainsi le bilan
    garde exactement la même forme que celui d'un vrai tri, même si de
    nouveaux compteurs apparaissent un jour.
    """
    return Report().to_dict()


def sort_session(session_dir: Path, library: Path, catalog, sur_mouvement=None) -> dict:
    """Range les fichiers de la session dans la bibliothèque. Renvoie le bilan détaillé.

    'sur_mouvement', si fourni, est transmis tel quel à sort_folder : il est
    appelé pour chaque fichier rencontré, avec le détail de son sort (issue
    #30, alimente le journal du serveur).
    """
    with _verrou:  # un seul tri à la fois
        report = sort_folder(session_dir, library, catalog, dry_run=False,
                             sur_mouvement=sur_mouvement)
    return report.to_dict()
