"""Sessions de synchro : réception des fichiers dans incoming/<session>/."""

import shutil
import uuid
from pathlib import Path


def new_session() -> str:
    """Identifiant de session (hex)."""
    return uuid.uuid4().hex


def _chemin_sur(base: Path, session: str, rel_path: str) -> Path:
    """Résout le chemin de destination en refusant toute sortie du dossier de session."""
    racine = (base / session).resolve()
    cible = (racine / rel_path).resolve()
    if not str(cible).startswith(str(racine) + "/") and cible != racine:
        raise ValueError(f"chemin non autorisé : {rel_path}")
    return cible


def save_upload(base: Path, session: str, rel_path: str, content: bytes) -> Path:
    """Écrit le fichier reçu sous incoming/<session>/<rel_path> (anti-traversée)."""
    if rel_path.startswith("/") or ".." in Path(rel_path).parts:
        raise ValueError(f"chemin non autorisé : {rel_path}")
    cible = _chemin_sur(base, session, rel_path)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(content)
    return cible


def cleanup(base: Path, session: str) -> None:
    """Supprime le dossier de session."""
    shutil.rmtree(base / session, ignore_errors=True)
