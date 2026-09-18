"""Constantes de configuration du trieur (extensions, mois, exclusions)."""

# Extensions reconnues (toujours en minuscules, avec le point).
PHOTO_EXTS: set[str] = {".png", ".jpg", ".jpeg", ".bmp", ".dng", ".heic", ".webp"}
VIDEO_EXTS: set[str] = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv", ".3gp"}

# Bruit à ne jamais ranger (nettoyé séparément, voir noise.py).
NOISE_EXTS: set[str] = {".opus", ".crypt14", ".nomedia"}

# Sous-dossiers WhatsApp volontairement exclus.
WHATSAPP_EXCLUDES: list[str] = [
    "Sent",
    "WhatsApp Animated Gifs",
    "WhatsApp Documents",
    "WhatsApp Stickers",
    "WhatsApp Video Notes",
]

# Mois en français (majuscules), pour les dossiers "MM MOIS".
MONTHS_FR: dict[int, str] = {
    1: "JANVIER", 2: "FEVRIER", 3: "MARS", 4: "AVRIL",
    5: "MAI", 6: "JUIN", 7: "JUILLET", 8: "AOUT",
    9: "SEPTEMBRE", 10: "OCTOBRE", 11: "NOVEMBRE", 12: "DECEMBRE",
}


def month_folder(month: int) -> str:
    """Renvoie le nom de dossier d'un mois, ex. 5 -> "05 MAI"."""
    return f"{month:02d} {MONTHS_FR[month]}"
