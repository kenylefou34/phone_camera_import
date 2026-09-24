"""Journal du serveur : synchronisations, mouvements de fichiers, événements (issue #30).

Base à part (~/phototheque_journal.db) : le catalogue appartient au trieur en
ligne de commande, la base des appareils est petite et sensible ; un journal
qui grossit n'a rien à faire dans l'une ou l'autre. Tout est gardé.
"""

import sqlite3
import threading
from datetime import datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS synchros (
  id TEXT PRIMARY KEY, appareil TEXT NOT NULL, label TEXT, adresse TEXT,
  debut TEXT NOT NULL, fin TEXT, paquets INTEGER DEFAULT 0,
  envoyes INTEGER DEFAULT 0, ranges INTEGER DEFAULT 0, doublons INTEGER DEFAULT 0,
  a_trier INTEGER DEFAULT 0, refuses INTEGER DEFAULT 0, erreurs INTEGER DEFAULT 0,
  octets INTEGER DEFAULT 0, app_echecs INTEGER, etat TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mouvements (
  id INTEGER PRIMARY KEY, synchro TEXT, session TEXT NOT NULL,
  horodatage TEXT NOT NULL, origine TEXT NOT NULL, taille INTEGER,
  empreinte TEXT, issue TEXT NOT NULL, destination TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS idx_mouvements_synchro ON mouvements(synchro);
CREATE INDEX IF NOT EXISTS idx_mouvements_session ON mouvements(session);
CREATE INDEX IF NOT EXISTS idx_mouvements_origine ON mouvements(origine);
CREATE INDEX IF NOT EXISTS idx_mouvements_empreinte ON mouvements(empreinte);
CREATE TABLE IF NOT EXISTS evenements (
  id INTEGER PRIMARY KEY, horodatage TEXT NOT NULL, type TEXT NOT NULL,
  appareil TEXT, adresse TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS commits (
  session TEXT PRIMARY KEY, synchro TEXT NOT NULL, horodatage TEXT NOT NULL);
"""


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _echapper_like(q: str) -> str:
    """Échappe %, _ et \\ pour qu'un motif de recherche reste littéral.

    Sans ça, une recherche contenant un joker SQL (ex. « % ») ramènerait
    n'importe quelle ligne au lieu de zéro résultat — un joker tapé par
    hasard ne doit jamais se comporter comme une recherche "tout".
    """
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Journal:
    """Le journal du serveur : synchronisations, mouvements, événements.

    Même schéma de connexion que DeviceStore : une connexion SQLite partagée
    entre les threads de requête (check_same_thread=False) protégée par un
    verrou qui sérialise tous les accès.

    Un mouvement est écrit PENDANT le tri, avant que la ligne de synchro
    n'existe encore (elle n'est créée qu'au commit) : sa colonne `synchro`
    reste NULL jusqu'à ce que `enregistrer_commit` la rattache via la
    colonne `session`, seule connue à ce moment-là.

    Chaque méthode d'écriture est UNE transaction entière, toujours sous le
    verrou : `with self._cx:` valide tout à la sortie normale du bloc, et
    annule tout (rollback) si une exception en sort. Sans ça, une requête qui
    levait au milieu d'une méthode laissait les précédentes en attente dans
    la connexion partagée — et l'écriture SUIVANTE, faite par n'importe quelle
    autre méthode, les validait à moitié (relecture finale, M2).
    """

    def __init__(self, db_path) -> None:
        self._cx = sqlite3.connect(str(db_path), check_same_thread=False)
        self._cx.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._cx.executescript(_SCHEMA)
            self._cx.commit()

    def evenement(self, type: str, appareil: str | None = None,
                  adresse: str | None = None, detail: str | None = None) -> None:
        """Trace un fait ponctuel (démarrage, appairage, révocation...)."""
        with self._lock, self._cx:
            self._cx.execute(
                "INSERT INTO evenements (horodatage, type, appareil, adresse, detail)"
                " VALUES (?,?,?,?,?)",
                (_maintenant(), type, appareil, adresse, detail),
            )

    def _inserer_mouvement(self, session: str, origine: str, taille, empreinte,
                            issue: str, destination, detail) -> None:
        """INSERT partagé par `ajouter_mouvement` et `noter_refus`.

        Le verrou ET la transaction sont tenus par l'appelant : cette méthode
        privée ne fait qu'exécuter la requête, pour ne pas dupliquer les neuf
        colonnes dans les deux méthodes publiques.
        """
        self._cx.execute(
            "INSERT INTO mouvements (synchro, session, horodatage, origine,"
            " taille, empreinte, issue, destination, detail)"
            " VALUES (NULL,?,?,?,?,?,?,?,?)",
            (session, _maintenant(), origine, taille, empreinte, issue, destination, detail),
        )

    def ajouter_mouvement(self, session: str, m: dict) -> None:
        """Enregistre le sort d'un fichier (dict produit par sort_folder, tâche 1).

        `synchro` reste NULL : ce mouvement n'est rattaché à une synchro que
        lors du commit qui le suit (voir `enregistrer_commit`).
        """
        with self._lock, self._cx:
            self._inserer_mouvement(
                session, m["origine"], m.get("taille"), m.get("empreinte"),
                m["issue"], m.get("destination"), m.get("detail"),
            )

    def noter_refus(self, session: str, origine: str, detail: str) -> None:
        """Un fichier refusé À L'ENVOI par le serveur (ex. extension inconnue).

        Issue 'refuse_envoi', DISTINCTE de 'refuse' (fichier reçu, puis ignoré
        par le trieur) : ce fichier-là n'a jamais été écrit sur le NUC ni vu
        par le trieur, donc il n'est pas dans le `ignores` du bilan — c'est
        la seule chose qui permet à `enregistrer_commit` de l'ajouter sans
        compter deux fois un fichier ignoré (relecture finale, M1).
        """
        with self._lock, self._cx:
            self._inserer_mouvement(session, origine, None, None, "refuse_envoi",
                                    None, detail)

    def enregistrer_commit(self, synchro: str, session: str, appareil: str,
                            label: str | None, adresse: str | None, bilan: dict,
                            bilan_app: dict | None) -> None:
        """Rattache un paquet (une session) à sa synchro, cumule le bilan.

        Plusieurs paquets peuvent partager le même identifiant `synchro` (une
        grosse sauvegarde découpée en paquets d'environ 500 Mo, cf. lot 1
        bis) : la ligne `synchros` n'est créée qu'au premier paquet
        (INSERT OR IGNORE), puis chaque paquet supplémentaire l'incrémente.

        `bilan.get(clé, 0)` partout : un vieux bilan sans `ignores` (avant la
        tâche 1) ne doit pas faire lever d'exception.

        Idempotent par session : si la réponse HTTP d'un /sync/commit se
        perd (WiFi instable du NUC), le client retente avec la MÊME session.
        Sans garde, ce rejeu doublerait tout le bilan cumulé (paquets,
        ranges, octets...) — la table `commits` retient les sessions déjà
        appliquées, et un rejeu ne recompte rien : la transaction se termine
        normalement, sans erreur visible côté client.
        """
        maintenant = _maintenant()
        # Une seule transaction pour les quatre requêtes (voir la docstring de
        # la classe) : si l'UPDATE final lève, la ligne `commits` insérée au
        # début est annulée avec le reste — sans quoi la session passerait
        # pour « déjà appliquée » et un nouvel essai ne recompterait jamais.
        with self._lock, self._cx:
            deja_connue = self._cx.execute(
                "INSERT OR IGNORE INTO commits (session, synchro, horodatage)"
                " VALUES (?,?,?)",
                (session, synchro, maintenant),
            ).rowcount == 0
            if deja_connue:
                return

            self._cx.execute(
                "INSERT OR IGNORE INTO synchros (id, appareil, label, adresse,"
                " debut, etat) VALUES (?,?,?,?,?, 'en cours')",
                (synchro, appareil, label, adresse, maintenant),
            )
            self._cx.execute(
                "UPDATE mouvements SET synchro=? WHERE session=? AND synchro IS NULL",
                (synchro, session),
            )
            # Seulement les refus À L'ENVOI : ceux du trieur (issue 'refuse')
            # sont déjà dans `ignores`, les recompter ici les doublait.
            refuses_envoi = self._cx.execute(
                "SELECT COUNT(*) FROM mouvements"
                " WHERE session=? AND issue='refuse_envoi'",
                (session,),
            ).fetchone()[0]

            refuses = bilan.get("ignores", 0) + refuses_envoi
            # Tout ce que le serveur a REÇU et que le trieur a vu passer, exclus
            # (`skipped`) compris : ils ont bien été envoyés, le trieur les a
            # seulement écartés. Les refus à l'envoi n'y sont pas — ils n'ont
            # jamais été écrits sur le NUC.
            envoyes = (bilan.get("sorted", 0) + bilan.get("to_triage", 0)
                       + bilan.get("duplicates", 0) + bilan.get("errors", 0)
                       + bilan.get("ignores", 0) + bilan.get("skipped", 0))

            champs = [
                "paquets = paquets + 1",
                "ranges = ranges + ?",
                "a_trier = a_trier + ?",
                "doublons = doublons + ?",
                "erreurs = erreurs + ?",
                "octets = octets + ?",
                "refuses = refuses + ?",
                "envoyes = envoyes + ?",
                "fin = ?",
                "etat = 'terminee'",
            ]
            valeurs = [
                bilan.get("sorted", 0),
                bilan.get("to_triage", 0),
                bilan.get("duplicates", 0),
                bilan.get("errors", 0),
                bilan.get("octets_ranges", 0),
                refuses,
                envoyes,
                maintenant,
            ]
            if bilan_app is not None:
                # Le téléphone envoie un cumul (pas un delta) : on écrase.
                champs.append("app_echecs = ?")
                valeurs.append(bilan_app.get("echecs", 0))
            if label is not None:
                champs.append("label = ?")
                valeurs.append(label)
            if adresse is not None:
                champs.append("adresse = ?")
                valeurs.append(adresse)
            valeurs.append(synchro)
            self._cx.execute(
                f"UPDATE synchros SET {', '.join(champs)} WHERE id=?", valeurs
            )

    def synchros(self, limite: int = 200) -> list[dict]:
        """Les synchros, plus récente d'abord."""
        with self._lock:
            lignes = self._cx.execute(
                "SELECT * FROM synchros ORDER BY debut DESC, rowid DESC LIMIT ?",
                (limite,),
            ).fetchall()
        return [dict(r) for r in lignes]

    def synchro(self, identifiant: str) -> dict | None:
        with self._lock:
            ligne = self._cx.execute(
                "SELECT * FROM synchros WHERE id=?", (identifiant,)
            ).fetchone()
        return dict(ligne) if ligne is not None else None

    def mouvements(self, synchro: str) -> list[dict]:
        """Les mouvements d'une synchro, dans l'ordre où ils ont été écrits."""
        with self._lock:
            lignes = self._cx.execute(
                "SELECT * FROM mouvements WHERE synchro=? ORDER BY id", (synchro,)
            ).fetchall()
        return [dict(r) for r in lignes]

    def rechercher(self, q: str, limite: int = 200) -> list[dict]:
        """Mouvements dont l'origine contient `q`, ou dont l'empreinte vaut `q`.

        `q` est échappé avant d'entrer dans le LIKE : un joker SQL tapé par
        l'utilisateur (« % », « _ ») doit rester un caractère littéral, pas
        un joker de la recherche elle-même.
        """
        motif = "%" + _echapper_like(q) + "%"
        with self._lock:
            lignes = self._cx.execute(
                "SELECT m.*, s.debut AS date_synchro FROM mouvements m"
                " LEFT JOIN synchros s ON s.id = m.synchro"
                " WHERE m.origine LIKE ? ESCAPE '\\' OR m.empreinte = ?"
                " ORDER BY m.id DESC LIMIT ?",
                (motif, q, limite),
            ).fetchall()
        return [dict(r) for r in lignes]

    def evenements(self, limite: int = 500) -> list[dict]:
        """Les événements, plus récent d'abord."""
        with self._lock:
            lignes = self._cx.execute(
                "SELECT * FROM evenements ORDER BY id DESC LIMIT ?", (limite,)
            ).fetchall()
        return [dict(r) for r in lignes]

    def close(self) -> None:
        self._cx.close()
