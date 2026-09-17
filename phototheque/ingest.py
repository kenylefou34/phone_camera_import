"""Intégration du trieur : range une session reçue, un tri à la fois."""

import threading
from pathlib import Path

from mediasort.sorter import sort_folder

_verrou = threading.Lock()


def sort_session(session_dir: Path, library: Path, catalog) -> dict:
    """Range les fichiers de la session dans la bibliothèque. Renvoie le bilan détaillé."""
    with _verrou:  # un seul tri à la fois
        report = sort_folder(session_dir, library, catalog, dry_run=False)
    return report.to_dict()
