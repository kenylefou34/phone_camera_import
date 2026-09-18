"""Mot de passe d'administration : empreinte et vérification.

Le mot de passe n'est jamais enregistré en clair. On stocke une empreinte
lente à calculer : une tentative coûte quelques dizaines de millisecondes au
serveur, ce qui rend une attaque par essais successifs inopérante sur un
réseau local, sans gêner la navigation.

Rien d'autre que la bibliothèque standard : le module `cryptography` est
absent du venv du NUC et doit le rester.
"""

import hashlib
import hmac
import secrets

# Ajusté à l'installation pour coûter environ 100 ms sur le NUC (2 cœurs).
ITERATIONS = 240_000
ALGO = "pbkdf2_sha256"


def empreinte(mot_de_passe: str, iterations: int = ITERATIONS) -> str:
    """Renvoie « pbkdf2_sha256$<itérations>$<sel>$<empreinte> ».

    Le sel est tiré au hasard : deux installations avec le même mot de passe
    n'ont pas la même empreinte. Le nombre d'itérations est stocké avec, pour
    pouvoir le durcir plus tard sans invalider les mots de passe existants.
    """
    sel = secrets.token_bytes(16)
    brut = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel, iterations)
    return f"{ALGO}${iterations}${sel.hex()}${brut.hex()}"


def verifier(mot_de_passe: str, enregistre: str) -> bool:
    """Vrai si le mot de passe correspond à l'empreinte enregistrée.

    Un enregistrement illisible (fichier tronqué, format inconnu, champ
    corrompu) fait échouer la vérification : en cas de doute on refuse, on ne
    laisse pas passer — et surtout on ne laisse remonter aucune exception, qui
    transformerait un fichier abîmé en erreur serveur.
    """
    # Hors du try : si l'appelant ne passe pas une chaîne, c'est SON bug, il
    # doit être visible plutôt qu'avalé en « mauvais mot de passe ».
    secret = mot_de_passe.encode()
    try:
        algo, iterations, sel_hex, attendu_hex = enregistre.split("$")
        if algo != ALGO:
            return False
        # Décodé ICI, dans le try : un champ non hexadécimal lève ValueError
        # et devient un refus propre. On compare ensuite des OCTETS et non des
        # chaînes hexadécimales : hmac.compare_digest refuse les str non-ASCII.
        attendu = bytes.fromhex(attendu_hex)
        brut = hashlib.pbkdf2_hmac(
            "sha256", secret, bytes.fromhex(sel_hex), int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    # Comparaison en temps constant : la durée de la réponse ne doit pas
    # révéler combien d'octets sont corrects.
    return hmac.compare_digest(brut, attendu)


UTILISATEUR_PAR_DEFAUT = "admin"


def utilisateur(fichier) -> str:
    """Identifiant d'administration enregistré, ou « admin » à défaut.

    Tout ce qui n'est pas un nom exploitable — fichier absent, vide, rempli
    d'espaces, illisible — retombe sur « admin ». C'est délibérément l'inverse
    de la règle appliquée au mot de passe, où le doute fait refuser : ici, un
    fichier abîmé ne doit jamais verrouiller le mainteneur dehors, car plus
    aucun identifiant ne fonctionnerait et il faudrait un accès SSH pour s'en
    sortir. Le mot de passe, lui, continue de protéger dans tous les cas —
    c'est lui le secret, pas ce nom.

    Les espaces autour sont retirés : le fichier est écrit par un script
    shell, une fin de ligne s'y glisse facilement, et personne ne pourrait
    taper le saut de ligne en trop.
    """
    try:
        nom = fichier.read_text().strip()
    except (OSError, ValueError):
        return UTILISATEUR_PAR_DEFAUT
    return nom or UTILISATEUR_PAR_DEFAUT
