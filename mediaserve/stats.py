"""Statistiques disque et médias + rendu d'un camembert SVG (côté serveur)."""

import math
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


def _arc(cx, cy, r, a0, a1):
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    grand = 1 if (a1 - a0) > math.pi else 0
    return f"M{cx},{cy} L{x0:.1f},{y0:.1f} A{r},{r} 0 {grand} 1 {x1:.1f},{y1:.1f} Z"


def pie_svg(used: int, free: int) -> str:
    """Camembert SVG utilisé (foncé) / libre (clair)."""
    total = used + free or 1
    a0 = -math.pi / 2
    a_used = a0 + 2 * math.pi * used / total
    p_used = _arc(60, 60, 55, a0, a_used)
    p_free = _arc(60, 60, 55, a_used, a0 + 2 * math.pi)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120">'
        f'<path d="{p_used}" fill="#3b6ea5"/><path d="{p_free}" fill="#d7e3f0"/></svg>'
    )
