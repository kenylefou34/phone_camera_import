"""Empreinte du certificat servi, transmise à l'application pour épinglage."""

import hashlib
import ssl
from pathlib import Path


def empreinte_certificat(chemin: Path) -> str:
    """Renvoie le SHA-256 du certificat au format DER, en hexadécimal.

    C'est la forme standard de l'épinglage : l'application compare cette
    empreinte à celle du certificat que lui présente le serveur qu'elle joint.
    Un appareil qui usurperait le nom du NUC serait rejeté, même avec un
    certificat par ailleurs valide.

    On passe par le format DER et non par le texte PEM : le PEM est un
    encodage, deux fichiers PEM différents (retours à la ligne, commentaires)
    peuvent porter le même certificat.
    """
    pem = Path(chemin).read_text()
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
