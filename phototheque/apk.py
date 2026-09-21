"""L'APK de l'application Android, déposé sur le NUC pour être téléchargé.

Pourquoi le serveur ne fabrique pas cet APK : le NUC n'a ni JDK ni SDK Android,
2 cœurs et 3 Go de mémoire. Le compiler là-bas n'est pas envisageable, et
l'embarquer dans le dépôt git y mettrait 25 Mo de binaire à chaque version.

Il est donc *déposé* depuis la machine de compilation par
`deploy/envoyer-apk.sh`, avec un petit fichier d'étiquette à côté :

    ~/.local/share/phototheque/app.apk
    ~/.local/share/phototheque/app.apk.infos.json

Ce module ne fait que lire ce qui est là. Il ne télécharge rien, ne compile
rien, et n'échoue jamais parce qu'une étiquette manque : c'est le binaire qui
compte, l'étiquette n'est qu'un confort.
"""

import json
import re
from datetime import datetime
from pathlib import Path

# Type MIME officiel d'un paquet Android. Sans lui, un navigateur propose
# d'ouvrir le fichier au lieu de l'enregistrer, et Android refuse de
# l'installer.
TYPE_MIME = "application/vnd.android.package-archive"

# Ce qu'on accepte de laisser passer dans un nom de fichier téléchargé. La
# version vient d'un fichier sur le disque : même écrit par notre propre
# script, il ne doit pas pouvoir injecter de retour à la ligne dans un en-tête
# HTTP ni de séparateur de chemin dans un nom de fichier.
_VERSION_SURE = re.compile(r"[^A-Za-z0-9._-]")


def fichier_infos(chemin_apk: Path) -> Path:
    """Le fichier d'étiquette qui accompagne l'APK."""
    return chemin_apk.with_name(chemin_apk.name + ".infos.json")


def infos(chemin_apk: Path) -> dict | None:
    """Ce qu'on sait de l'APK déposé, ou None s'il n'y en a pas.

    None signifie « aucun APK », jamais « APK illisible » : un service
    fraîchement installé n'en a pas, et ce n'est pas une panne.

    La TAILLE est toujours relue sur le disque et jamais reprise de
    l'étiquette. Un dépôt interrompu laisserait un binaire tronqué sous une
    étiquette annonçant la taille complète — et la page d'administration
    afficherait sereinement 25 Mo pour un fichier qui n'en fait que 3.
    """
    if not chemin_apk.is_file():
        return None

    etat = chemin_apk.stat()
    vu = {
        "version": None,
        "version_code": None,
        "construit_le": None,
        "sha256": None,
        "octets": etat.st_size,
        "depose_le": datetime.fromtimestamp(etat.st_mtime).isoformat(
            timespec="seconds"),
    }

    try:
        etiquette = json.loads(fichier_infos(chemin_apk).read_text())
    except (OSError, ValueError):
        # Étiquette absente ou illisible : on perd le confort, jamais le
        # binaire. Refuser de servir un APK présent parce qu'il manque un
        # fichier annexe laisserait le mainteneur sans application et sans
        # explication.
        return vu

    if isinstance(etiquette, dict):
        for cle in ("version", "version_code", "construit_le", "sha256"):
            if etiquette.get(cle) is not None:
                vu[cle] = etiquette[cle]
    return vu


def nom_de_telechargement(vu: dict) -> str:
    """Nom du fichier proposé au navigateur.

    La version y figure pour que deux téléchargements successifs ne se
    confondent pas dans le dossier du téléphone — Android nommerait sinon le
    second « app(1).apk », et on installerait l'ancien sans s'en apercevoir.
    """
    version = vu.get("version")
    if not version:
        return "phototheque.apk"
    return f"phototheque-{_VERSION_SURE.sub('_', str(version))}.apk"
