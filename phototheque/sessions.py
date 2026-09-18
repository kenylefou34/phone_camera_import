"""Sessions de synchro : réception des fichiers dans incoming/<session>/."""

import re
import shutil
import uuid
from pathlib import Path

# Taille des blocs lus puis écrits. Même valeur que mediasort.hashing : c'est
# le compromis déjà éprouvé du projet entre nombre d'appels système et mémoire
# retenue. Ce qui compte ici est qu'elle soit BORNÉE — le NUC a 1,7 Gio
# disponible et reçoit des vidéos de plusieurs gigaoctets (issue #21).
TAILLE_BLOC = 1024 * 1024      # 1 Mio

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


def save_upload(base: Path, session: str, rel_path: str, flux) -> Path:
    """Écrit le fichier reçu sous incoming/<session>/<rel_path> (anti-traversée).

    `flux` est un objet de lecture (`.read(taille)`), pas un bloc d'octets : le
    fichier est recopié PAR BLOCS et n'est jamais tenu en mémoire dans son
    entier. Le NUC dispose de 1,7 Gio et reçoit des vidéos de plus de 3 Gio ;
    la version précédente le faisait tuer par le noyau, redémarrer, puis
    recommencer sur le même fichier — une boucle dont le symptôme (service qui
    redémarre) ne désignait jamais la cause (issue #21).

    Les contrôles de chemin restent AVANT la moindre écriture : les faire après
    aurait déjà créé le dossier, voire le fichier, à l'endroit interdit.

    L'écriture passe par un fichier « .partiel » renommé à la fin. Une coupure
    en cours d'envoi ne laisse donc rien à l'emplacement final : un fichier
    tronqué portant une extension de média serait pris pour un média valide par
    le trieur, rangé dans la bibliothèque, compté comme reçu — et l'original,
    sur le téléphone, ne serait plus jamais proposé. Le suffixe « .partiel »
    protège d'ailleurs deux fois : le trieur ignore les extensions qu'il ne
    connaît pas, donc même un reliquat laissé par un processus tué ne sera
    jamais rangé.
    """
    _verifier_session(session)
    if rel_path.startswith("/") or ".." in Path(rel_path).parts:
        raise ValueError(f"chemin non autorisé : {rel_path}")
    cible = _chemin_sur(base, session, rel_path)
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = cible.with_name(cible.name + ".partiel")
    try:
        with open(partiel, "wb") as sortie:
            shutil.copyfileobj(flux, sortie, TAILLE_BLOC)
    except BaseException:
        # BaseException et non Exception : une coupure de service ou un
        # KeyboardInterrupt ne doivent pas non plus laisser de reliquat.
        partiel.unlink(missing_ok=True)
        raise
    partiel.replace(cible)      # renommage atomique : le fichier apparaît entier
    return cible


def cleanup(base: Path, session: str) -> None:
    """Supprime le dossier de session."""
    _verifier_session(session)
    shutil.rmtree(base / session, ignore_errors=True)
