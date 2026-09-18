"""Limitation des essais d'authentification (issue #19).

Le mot de passe d'administration est protégé par une empreinte lente à
calculer : environ 100 ms sur les deux cœurs du NUC. C'était la seule défense,
et elle a un défaut — **ce coût est payé par le serveur**. Quelques dizaines de
requêtes simultanées suffisent à occuper les deux cœurs à calculer des
empreintes, et le tri des médias tourne dans le même processus, derrière un
verrou. Saturer l'authentification revenait donc à ralentir l'import, sans
connaître le moindre mot de passe.

D'où la règle centrale : au-delà du seuil, **le refus tombe sans calculer quoi
que ce soit**. C'est ce qui rend l'acharnement inintéressant.

Deux garde-fous, pour que la protection ne se retourne pas contre le
mainteneur :

- le décompte est **par machine d'origine** — sinon quelques essais ratés
  depuis n'importe quel appareil du réseau fermeraient l'administration à son
  propriétaire, ce qui offrirait à l'attaquant le déni de service qu'on essaie
  d'empêcher ;
- l'attente est **plafonnée** et s'écoule d'elle-même : jamais de blocage ferme.
  Une nuit d'essais ne doit pas fermer l'administration pour des jours — cela
  ne punirait que le mainteneur, l'attaquant étant déjà parti.

Limite connue : le décompte vit en mémoire du processus. Il repart donc à zéro
à chaque redémarrage du service, et serait faux si le service tournait un jour
avec plusieurs workers — c'est exactement le sujet de l'issue #17, qui traite
le même problème pour l'appairage en cours.
"""

import threading
from collections import OrderedDict

SEUIL = 5               # essais ratés tolérés sans aucune attente
DELAI_BASE = 2.0        # secondes d'attente au premier dépassement
DELAI_MAX = 60.0        # plafond : au-delà, on punirait surtout le mainteneur
MAX_SOURCES = 1024      # bornage de la table (voir _menage)


class Limiteur:
    """Compte les échecs par source et impose une attente croissante."""

    def __init__(self, seuil: int = SEUIL, delai_base: float = DELAI_BASE,
                 delai_max: float = DELAI_MAX, max_sources: int = MAX_SOURCES):
        self._seuil = seuil
        self._delai_base = delai_base
        self._delai_max = delai_max
        self._max_sources = max_sources
        # source -> (nombre d'échecs consécutifs, instant du dernier)
        # OrderedDict : l'ordre d'insertion sert au ménage, la plus ancienne
        # source vue étant la première sacrifiée.
        self._sources: OrderedDict = OrderedDict()
        # Le serveur traite les requêtes dans plusieurs fils d'exécution
        # (FastAPI exécute les endpoints synchrones dans un pool) : sans
        # verrou, deux essais simultanés pourraient s'écraser mutuellement et
        # le décompte reculerait au lieu d'avancer.
        self._verrou = threading.Lock()

    def __len__(self) -> int:
        return len(self._sources)

    def _delai(self, nb_echecs: int) -> float:
        """Attente due après `nb_echecs` échecs : double à chaque fois."""
        # +1 : au tout premier dépassement (nb_echecs == seuil) on veut
        # exactement delai_base, pas sa moitié. Sans ce décalage, la suite
        # doublait correctement mais partait un cran trop bas — invisible
        # pour un test de croissance, visible dans le « Retry-After » envoyé.
        depassement = nb_echecs - self._seuil + 1      # 1 au premier dépassement
        return min(self._delai_max, self._delai_base * 2 ** (depassement - 1))

    def doit_attendre(self, source: str, maintenant: float) -> float:
        """Secondes restant à patienter pour cette source ; 0 si elle peut essayer.

        À appeler AVANT toute vérification de mot de passe : c'est tout l'objet
        de la limitation que de ne rien calculer quand la réponse est déjà non.
        """
        with self._verrou:
            entree = self._sources.get(source)
            if entree is None:
                return 0.0
            nb_echecs, dernier = entree
            if nb_echecs < self._seuil:
                return 0.0
            reste = dernier + self._delai(nb_echecs) - maintenant
            return max(0.0, reste)

    def echec(self, source: str, maintenant: float) -> int:
        """Enregistre un essai raté. Renvoie le nombre d'échecs consécutifs."""
        with self._verrou:
            nb_echecs, _ = self._sources.pop(source, (0, 0.0))
            nb_echecs += 1
            self._sources[source] = (nb_echecs, maintenant)   # réinséré = récent
            self._menage()
            return nb_echecs

    def succes(self, source: str) -> None:
        """Efface l'ardoise : le mainteneur ne traîne pas ses erreurs de la veille."""
        with self._verrou:
            self._sources.pop(source, None)

    def _menage(self) -> None:
        """Borne la table. Appelée avec le verrou déjà tenu.

        Une ligne par adresse vue serait une fuite de mémoire offerte : sur une
        machine de 3 Gio, ce serait un second moyen de la faire tomber, à la
        place de celui qu'on vient de fermer. On sacrifie les sources vues il y
        a le plus longtemps — jamais celle qui vient d'échouer, qui est
        justement celle qu'il faut retenir.
        """
        while len(self._sources) > self._max_sources:
            self._sources.popitem(last=False)
