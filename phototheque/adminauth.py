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


class CacheVerifications:
    """Mémoire courte des vérifications RÉUSSIES (relecture finale #31, I1).

    Pourquoi : `verifier` coûte un PBKDF2 de 240 000 itérations (~100 ms sur
    le NUC). Le navigateur renvoie l'en-tête Basic à CHAQUE requête, et une
    grille de la galerie, c'est 1 page + jusqu'à 120 vignettes : plusieurs
    secondes de calcul des deux cœurs, dans le processus même qui reçoit les
    photos du téléphone.

    Pourquoi c'est sûr :
    - seules les RÉUSSITES sont retenues ; un échec repasse toujours par la
      vérification complète ET par le limiteur d'essais (essais.py), qui ne
      change pas ;
    - on ne garde jamais l'en-tête lui-même, seulement son empreinte SHA-256
      (le mot de passe n'est donc pas en clair dans la mémoire du cache) ;
    - la clé inclut la date de modification des fichiers de mot de passe et
      d'identifiant : `identifiants.sh` réécrit ces fichiers, et l'ancien mot
      de passe cesse d'être accepté dès la requête suivante ;
    - durée de vie courte (DUREE_S) et taille bornée (TAILLE) : une entrée
      ne survit ni longtemps, ni en nombre ;
    - comparaison en temps constant (`hmac.compare_digest`).

    Accès sous verrou : FastAPI exécute les routes synchrones dans plusieurs
    fils d'exécution à la fois.
    """

    DUREE_S = 300
    TAILLE = 16

    def __init__(self, taille: int = TAILLE, duree_s: float = DUREE_S,
                 maintenant=None) -> None:
        import threading
        import time
        self._taille, self._duree = taille, duree_s
        self._maintenant = maintenant or time.monotonic
        self._verrou = threading.Lock()
        # Liste de (empreinte de l'en-tête, signature des fichiers, expiration),
        # la plus ancienne en tête.
        self._entrees: list[tuple[bytes, tuple, float]] = []

    @staticmethod
    def _empreinte(entete: str) -> bytes:
        return hashlib.sha256(entete.encode()).digest()

    def connu(self, entete: str, signature: tuple) -> bool:
        """Vrai si cet en-tête exact a réussi récemment, avec ces mêmes fichiers."""
        cle = self._empreinte(entete)
        with self._verrou:
            t = self._maintenant()
            self._entrees = [e for e in self._entrees if e[2] > t]
            trouve = False
            for empreinte_e, signature_e, _ in self._entrees:
                # Pas de sortie anticipée : toutes les entrées sont comparées.
                if hmac.compare_digest(empreinte_e, cle) and signature_e == signature:
                    trouve = True
            return trouve

    def retenir(self, entete: str, signature: tuple) -> None:
        """Retient une vérification RÉUSSIE (n'appeler que dans ce cas)."""
        cle = self._empreinte(entete)
        with self._verrou:
            t = self._maintenant()
            self._entrees = [e for e in self._entrees
                             if e[2] > t and not hmac.compare_digest(e[0], cle)]
            self._entrees.append((cle, signature, t + self._duree))
            del self._entrees[:-self._taille]      # les plus vieilles sortent
