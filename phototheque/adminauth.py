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

    Un enregistrement illisible (fichier tronqué, format inconnu) fait
    échouer la vérification : en cas de doute on refuse, on ne laisse pas
    passer.
    """
    try:
        algo, iterations, sel_hex, attendu_hex = enregistre.split("$")
        if algo != ALGO:
            return False
        brut = hashlib.pbkdf2_hmac(
            "sha256", mot_de_passe.encode(), bytes.fromhex(sel_hex), int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    # Comparaison en temps constant : la durée de la réponse ne doit pas
    # révéler combien de caractères sont corrects.
    return hmac.compare_digest(brut.hex(), attendu_hex)
