"""Sessions de synchro : réception des fichiers dans incoming/<session>/."""

import logging
import re
import shutil
import time
import uuid
from pathlib import Path

# Une purge qui casse sur UNE session (disque NTFS externe capricieux,
# permissions, course avec une autre synchro) n'a droit qu'à une ligne ici :
# elle ne doit jamais remonter jusqu'à l'appelant (voir purger_abandonnees).
_log = logging.getLogger("phototheque.sessions")

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


def _lister_fichiers(dossier: Path) -> list[tuple[str, int]]:
    """Les fichiers sous `dossier` : (chemin relatif à `dossier`, taille).

    Le chemin est relatif et en « / » (`as_posix`) : c'est exactement le
    `path` qu'avait envoyé le téléphone, donc ce que le mainteneur tapera
    dans la recherche de l'historique.

    Un fichier qui disparaît ENTRE le listage (`rglob`) et le `stat()` qui lit
    sa taille — course avec une autre synchro qui déplace ses fichiers, ou un
    « .partiel » renommé au même instant — est compté pour ce qu'il est
    devenu : absent. On rend ce qu'on a pu lister plutôt que de faire échouer
    tout l'inventaire pour UNE entrée qui n'existe déjà plus.
    """
    fichiers = []
    for p in dossier.rglob("*"):
        if not p.is_file():
            continue
        try:
            taille = p.stat().st_size
        except OSError:
            continue
        fichiers.append((p.relative_to(dossier).as_posix(), taille))
    return fichiers


def _mtime_le_plus_recent(dossier: Path) -> float:
    """Date de modification la plus récente de `dossier` et de tout son contenu.

    `dossier` lui-même doit exister (son `stat()` n'est pas protégé : s'il a
    disparu, il n'y a de toute façon plus rien à purger — l'appelant attrape
    l'exception). En revanche une entrée sous `dossier` qui disparaît PENDANT
    le parcours (même course que dans `_lister_fichiers`) est ignorée pour la datation :
    elle n'existe plus, elle ne peut donc plus dater quoi que ce soit. Sans ce
    filtrage, une session qui reçoit régulièrement des fichiers éphémères
    (« .partiel » renommés pendant qu'on purge) ne serait JAMAIS purgeable :
    chaque passe retomberait sur la même course et échouerait de nouveau.
    """
    plus_recent = dossier.stat().st_mtime
    for p in dossier.rglob("*"):
        try:
            plus_recent = max(plus_recent, p.stat().st_mtime)
        except FileNotFoundError:
            continue
    return plus_recent


def purger_abandonnees(base: Path, age_max_s: float = 24 * 3600,
                        maintenant: float | None = None,
                        avant_suppression=None) -> list[dict]:
    """Supprime les dossiers de session abandonnés depuis plus de `age_max_s`.

    `avant_suppression(session, fichiers)`, si fourni, est appelé pour chaque
    session JUSTE AVANT son `rmtree`, avec la liste nominative de ses fichiers
    (`_lister_fichiers` : chemin relatif, taille) — pendant qu'ils existent
    encore (relecture finale, I2). C'est ainsi que l'application écrit un
    mouvement par fichier supprimé et retient la session comme retirée, sans
    que ce module ait à connaître le journal. Le rappel ne doit pas lever :
    s'il levait quand même une `OSError`, la session serait laissée en place
    (même traitement qu'une panne de disque), et toute autre exception
    remonterait à l'appelant.

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

    CHAQUE session est traitée dans son propre `try/except OSError` : sans
    ça, une seule session à problème (stat impossible, `rmtree` qui casse sur
    le disque externe NTFS) faisait lever toute la fonction — perdant au
    passage la liste des sessions DÉJÀ purgées dans cette même passe (rien
    n'était encore rendu), et laissant les sessions suivantes intactes pour
    toujours puisque l'itération est triée et retombe sur la même en tête à
    chaque appel. Une session qui échoue est simplement journalisée et
    laissée en place : la prochaine passe retentera.
    """
    if maintenant is None:
        maintenant = time.time()
    if not base.is_dir():
        return []
    emportees = []
    for dossier in sorted(base.iterdir()):
        if not dossier.is_dir() or not identifiant_valide(dossier.name):
            continue
        try:
            plus_recent = _mtime_le_plus_recent(dossier)
            if maintenant - plus_recent <= age_max_s:
                continue
            fichiers = _lister_fichiers(dossier)
            if avant_suppression is not None:
                avant_suppression(dossier.name, fichiers)
            shutil.rmtree(dossier)
        except OSError:
            _log.exception("purge de la session %s impossible, poursuite avec les suivantes",
                           dossier.name)
            continue
        # Ajouté seulement APRÈS un rmtree réussi : une session qu'on n'a pas
        # su supprimer ne doit jamais apparaître comme retirée.
        emportees.append({"session": dossier.name, "fichiers": len(fichiers),
                          "octets": sum(taille for _, taille in fichiers)})
    return emportees


def abandonner(base: Path, session: str, avant_suppression=None) -> dict:
    """Supprime la session `session` sur demande explicite du téléphone
    (bouton « Interrompre », `POST /sync/abandon`), et rend ce qui a été
    supprimé.

    `avant_suppression(session, fichiers)` : même rappel que pour
    `purger_abandonnees`, appelé juste avant la suppression — y compris pour
    une session SANS dossier (abandonnée avant le moindre envoi), avec une
    liste vide : elle n'a rien à tracer fichier par fichier, mais elle doit
    quand même être retenue comme retirée (un commit ultérieur sur elle sera
    refusé, voir `sync_commit`).

    Le contrôle de forme est fait EN PREMIER, avant même de regarder le
    disque : un identifiant hors norme ne doit strictement rien supprimer, ni
    même être parcouru.

    Un identifiant valide qui désigne un LIEN SYMBOLIQUE n'est jamais produit
    par ce service (`save_upload` ne crée que des dossiers) : on ne supprime
    rien et on ne compte rien plutôt que de suivre le lien et de rendre un
    bilan qui MENT sur ce qui a réellement disparu — `shutil.rmtree` refuse
    déjà d'agir sur un lien, mais en silence (`cleanup` l'appelle avec
    `ignore_errors=True`), ce qui ne suffit pas à garantir un compte rendu
    honnête si on avait déjà compté à travers le lien avant.

    Une panne de disque pendant le seul INVENTAIRE (avant toute suppression)
    ne doit jamais faire échouer la route `/sync/abandon` avec une 500 : on
    compte ce qu'on peut, zéro si même regarder le dossier échoue, et on
    tente quand même le nettoyage.
    """
    _verifier_session(session)
    dossier = base / session
    if dossier.is_symlink():
        return {"supprimes": 0, "octets": 0}
    try:
        fichiers = _lister_fichiers(dossier) if dossier.is_dir() else []
    except OSError:
        fichiers = []
    if avant_suppression is not None:
        avant_suppression(session, fichiers)
    cleanup(base, session)
    return {"supprimes": len(fichiers), "octets": sum(taille for _, taille in fichiers)}
