"""Sessions de synchro : réception des fichiers dans incoming/<session>/."""

import re
import shutil
import uuid
from pathlib import Path

# La forme exacte de ce que produit new_session() : 32 caractères
# hexadécimaux minuscules. Tout ce qui s'en écarte est refusé — voir
# identifiant_valide().
_FORME_IDENTIFIANT = re.compile(r"[0-9a-f]{32}")


def new_session() -> str:
    """Identifiant de session (hex)."""
    return uuid.uuid4().hex


def identifiant_valide(session: str) -> bool:
    """Vrai si la chaîne a bien la forme produite par new_session().

    L'identifiant de session devient un nom de dossier : sans ce contrôle,
    une session « .. » ferait écrire à côté du dépôt des envois — et surtout
    effacer ce dossier voisin au nettoyage de fin de synchro, qui supprime
    récursivement. On n'accepte donc que la forme qu'on fabrique soi-même,
    qui ne peut contenir ni séparateur ni point.
    """
    return isinstance(session, str) and bool(_FORME_IDENTIFIANT.fullmatch(session))


def _verifier_session(session: str) -> None:
    """Refuse un identifiant de session hors norme."""
    if not identifiant_valide(session):
        raise ValueError(f"identifiant de session non autorisé : {session!r}")


def _chemin_sur(base: Path, session: str, rel_path: str) -> Path:
    """Résout le chemin de destination en refusant toute sortie du dossier de session."""
    racine = (base / session).resolve()
    cible = (racine / rel_path).resolve()
    if not str(cible).startswith(str(racine) + "/") and cible != racine:
        raise ValueError(f"chemin non autorisé : {rel_path}")
    return cible


def save_upload(base: Path, session: str, rel_path: str, content: bytes) -> Path:
    """Écrit le fichier reçu sous incoming/<session>/<rel_path> (anti-traversée)."""
    _verifier_session(session)
    if rel_path.startswith("/") or ".." in Path(rel_path).parts:
        raise ValueError(f"chemin non autorisé : {rel_path}")
    cible = _chemin_sur(base, session, rel_path)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(content)
    return cible


def cleanup(base: Path, session: str) -> None:
    """Supprime le dossier de session."""
    _verifier_session(session)
    shutil.rmtree(base / session, ignore_errors=True)
