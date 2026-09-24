"""Sessions de synchro : réception des fichiers dans incoming/<session>/."""

import re
import shutil
import time
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


def _inventaire(dossier: Path) -> tuple[int, int]:
    """(nombre de fichiers, octets) sous `dossier`, lui compris s'il en contient."""
    fichiers = [p for p in dossier.rglob("*") if p.is_file()]
    return len(fichiers), sum(p.stat().st_size for p in fichiers)


def purger_abandonnees(base: Path, age_max_s: float = 24 * 3600,
                        maintenant: float | None = None) -> list[dict]:
    """Supprime les dossiers de session abandonnés depuis plus de `age_max_s`.

    Ne considère QUE les dossiers dont le nom passe `identifiant_valide` :
    c'est ce qui écarte `_echecs` (quarantaine des médias non rangés, issue
    #16) par construction, sans avoir à le nommer explicitement nulle part —
    tout dossier qui n'a pas exactement la forme produite par `new_session()`
    est ignoré, purge ou pas. Une base absente (service jamais utilisé) rend
    simplement une liste vide.

    L'âge retenu est celui du fichier LE PLUS RÉCENT de toute l'arborescence
    (le dossier de session lui-même compris, `rglob("*")` pour le reste) : une
    réception en cours écrit dans un sous-dossier
    (`<session>/DCIM/Camera/...`) sans jamais rafraîchir la date du dossier de
    session — s'appuyer sur cette seule date purgerait une session dont un
    transfert est toujours en train d'arriver.
    """
    if maintenant is None:
        maintenant = time.time()
    if not base.is_dir():
        return []
    emportees = []
    for dossier in sorted(base.iterdir()):
        if not dossier.is_dir() or not identifiant_valide(dossier.name):
            continue
        plus_recent = max(p.stat().st_mtime for p in [dossier, *dossier.rglob("*")])
        if maintenant - plus_recent <= age_max_s:
            continue
        fichiers, octets = _inventaire(dossier)
        emportees.append({"session": dossier.name, "fichiers": fichiers, "octets": octets})
        shutil.rmtree(dossier)
    return emportees


def abandonner(base: Path, session: str) -> dict:
    """Supprime la session `session` sur demande explicite du téléphone
    (bouton « Interrompre », `POST /sync/abandon`), et rend ce qui a été
    supprimé.

    Le contrôle de forme est fait EN PREMIER, avant même de regarder le
    disque : un identifiant hors norme ne doit strictement rien supprimer, ni
    même être parcouru.
    """
    _verifier_session(session)
    dossier = base / session
    fichiers, octets = _inventaire(dossier) if dossier.is_dir() else (0, 0)
    cleanup(base, session)
    return {"supprimes": fichiers, "octets": octets}
