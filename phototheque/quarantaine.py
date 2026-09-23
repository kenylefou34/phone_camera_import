"""Mise à l'abri des médias qu'un tri n'a pas su ranger (issue #16).

Avant cette quarantaine, `POST /sync/commit` rangeait ce qu'il pouvait puis
supprimait le dossier de session SANS REGARDER LE BILAN. Or un fichier en échec
y reste : il était donc détruit. L'horizon, lui, n'avançait pas — le téléphone
reproposait le média à la synchro suivante — mais cette garantie repose
entièrement sur un tiers. Une application qui libère la place après envoi, un
DCIM vidé à la main, un nettoyeur de stockage, et l'unique copie restante venait
d'être détruite par le serveur lui-même.
"""

import datetime
import json
import shutil
from pathlib import Path

from mediasort.hashing import file_hash


# Suffixe du fichier compagnon qui porte la raison de l'échec. Un fichier mis de
# côté sans sa raison ne se diagnostique plus après coup — et c'est justement
# après coup qu'on regarde. Un compagnon plutôt qu'un index unique : il n'y a
# alors rien qui puisse se désynchroniser du fichier qu'il décrit.
MOTIF = ".motif"

# Nom du dossier d'abri, sous INCOMING_DIR. Il ne peut JAMAIS entrer en
# collision avec une session : `sessions.identifiant_valide` n'accepte que 32
# caractères hexadécimaux, donc ni `sessions.cleanup` ni un identifiant
# fantaisiste ne peuvent le viser.
DOSSIER = "_echecs"


def _chemin_libre(cible: Path) -> Path:
    """Suffixe _1, _2... tant que le nom est pris."""
    n = 1
    candidat = cible
    while candidat.exists():
        candidat = cible.with_name(f"{cible.stem}_{n}{cible.suffix}")
        n += 1
    return candidat


def mettre_de_cote(session_dir: Path, echecs: list[dict], abri: Path) -> None:
    """Déplace hors de la session les fichiers que le tri n'a pas su ranger.

    `echecs` est la liste nommée du bilan (voir `mediasort.sorter.Report`) :
    elle seule dit quoi sauver. Ce qui RESTE dans le dossier de session
    contient aussi les doublons et le bruit exclu, que le nettoyage a raison de
    détruire — les mettre à l'abri remplirait le disque de médias déjà rangés.

    Un DÉPLACEMENT, pas une copie : le dossier des envois et la bibliothèque
    sont sur le même disque, l'opération est donc instantanée et ne consomme
    aucun espace supplémentaire.
    """
    for echec in echecs:
        source = session_dir / echec["fichier"]
        if not source.exists():
            continue
        cible = abri / echec["fichier"]
        cible.parent.mkdir(parents=True, exist_ok=True)
        if cible.exists():
            # Le nom est pris. Deux cas, et les confondre serait grave.
            if file_hash(source) == file_hash(cible):
                # Même contenu : c'est la énième tentative du MÊME média, que
                # le téléphone renvoie chaque nuit puisque l'horizon n'avance
                # pas. On garde l'exemplaire déjà à l'abri — sa date est la
                # trace utile — et on laisse tomber celui-ci. Sans cette borne,
                # une vidéo de 3 Go en échec ferait 90 Go par mois.
                source.unlink()
                continue
            # Contenus différents : deux médias distincts portent le même
            # chemin. Écraser ici détruirait un média, exactement ce que cette
            # quarantaine existe pour empêcher.
            cible = _chemin_libre(cible)
        # shutil.move et non Path.replace : `replace` échoue entre deux systèmes
        # de fichiers, ce qui arriverait si INCOMING_DIR était un jour déplacé
        # hors du disque de la bibliothèque.
        shutil.move(str(source), str(cible))
        cible.with_name(cible.name + MOTIF).write_text(json.dumps({
            "raison": echec.get("raison", ""),
            "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        }), encoding="utf-8")


def lister(abri: Path) -> list[dict]:
    """Ce que contient la quarantaine : chemin, raison, taille, date.

    Un abri absent n'est pas une anomalie, c'est le cas NORMAL : aucun échec
    n'a jamais eu lieu. Lever ici ferait échouer la page d'administration sur
    un serveur en parfait état.
    """
    if not abri.is_dir():
        return []
    entrees = []
    for chemin in sorted(abri.rglob("*")):
        if not chemin.is_file() or chemin.name.endswith(MOTIF):
            continue
        compagnon = chemin.with_name(chemin.name + MOTIF)
        try:
            detail = json.loads(compagnon.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Compagnon perdu ou illisible : on montre quand même le fichier.
            # Le taire reviendrait à cacher un média en péril.
            detail = {}
        entrees.append({
            "fichier": chemin.relative_to(abri).as_posix(),
            "raison": detail.get("raison", "raison inconnue"),
            "date": detail.get("date", ""),
            "octets": chemin.stat().st_size,
        })
    return entrees


def purger(abri: Path) -> int:
    """Vide la quarantaine. Renvoie le nombre de médias retirés.

    La purge est MANUELLE, et c'est un choix. Une purge à l'ancienneté
    réintroduirait exactement le défaut qu'on corrige, avec un délai : elle
    détruirait des médias que le serveur n'a pas rangés, sans que personne ne
    l'ait demandé. Ce dossier ne grossit que quand quelque chose ne va pas ;
    qu'il grossisse est un signal, pas un déchet.
    """
    entrees = lister(abri)
    if entrees:
        shutil.rmtree(abri, ignore_errors=True)
    return len(entrees)
