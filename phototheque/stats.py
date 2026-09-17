"""Statistiques disque et médias du service."""

import shutil
import sqlite3
from pathlib import Path

from mediasort.classify import media_type


def disk_stats(path: Path) -> dict:
    """Espace du disque contenant 'path'."""
    u = shutil.disk_usage(str(path))
    pct = round(100 * u.used / u.total) if u.total else 0
    return {"total": u.total, "utilise": u.used, "libre": u.free, "pourcentage_utilise": pct}


def media_stats(catalog_db: Path) -> dict:
    """Compte photos/vidéos au catalogue (déduit du type d'extension du chemin)."""
    photos = videos = 0
    cx = sqlite3.connect(str(catalog_db))
    try:
        for (chemin,) in cx.execute("SELECT chemin FROM medias"):
            t = media_type(Path(chemin).suffix)
            if t == "photo":
                photos += 1
            elif t == "video":
                videos += 1
    finally:
        cx.close()
    return {"photos": photos, "videos": videos}


def disk_level(pourcentage: int) -> str:
    """Niveau d'occupation du disque : "ok", "warning" ou "critical".

    Calculé à part pour être testable et pour que la page puisse en tirer un
    MOT en plus d'une couleur : une couleur d'état ne doit jamais porter
    l'information seule (daltonisme, impression, contraste forcé).
    """
    if pourcentage >= 90:
        return "critical"
    if pourcentage >= 80:
        return "warning"
    return "ok"
