# Journal serveur et sessions abandonnées — plan d'implémentation (issue #30)

> **Pour les agents :** SOUS-SKILL REQUIS : superpowers:subagent-driven-development
> (recommandé) ou superpowers:executing-plans, tâche par tâche. Les étapes
> utilisent des cases à cocher (`- [ ]`).

**But :** que le serveur se souvienne de chaque synchronisation (qui, quand, quoi,
où c'est rangé, ce qui ne l'a pas été), le montre sous mot de passe, et nettoie
les sessions abandonnées au lieu de les laisser pourrir dans `incoming/`.

**Architecture :** une nouvelle base SQLite `~/phototheque_journal.db`
(module `phototheque/journal.py`), alimentée au fil du tri par un consommateur
que `mediasort.sorter.sort_folder` appelle pour chaque fichier. Le commit
regroupe ses paquets en une ligne de synchronisation grâce à un identifiant
envoyé par l'application. Une purge à l'ancienneté des dossiers de session
tourne au démarrage et après chaque commit. Quatre pages d'admin en lecture.

**Technologies :** Python 3.14, FastAPI, SQLite (stdlib), pytest ; Kotlin +
kotlinx.serialization côté application (tâche 7).

**Spec :** `docs/superpowers/specs/2026-09-21-serveur-journal-et-sessions-design.md`
— écrite le 21/09, **avant** le lot 2 et la quarantaine de #16. Ce plan
l'adapte ; les écarts sont listés ci-dessous et justifiés.

## Écarts assumés par rapport à la spec

1. **`mouvements.synchro` peut être NULL, et une colonne `session` s'ajoute.**
   Les mouvements sont écrits PENDANT le tri, avant que la ligne de synchro
   n'existe, et un refus d'extension arrive dès `/sync/upload`, où seul
   l'identifiant de session est connu. Le commit rattache ensuite
   `UPDATE mouvements SET synchro=? WHERE session=? AND synchro IS NULL`.
2. **Issue supplémentaire `exclu`** pour les fichiers des sous-dossiers WhatsApp
   exclus (`classify.is_excluded`) : ils sont aujourd'hui comptés dans
   `skipped` sans trace nominative, et les appeler « refusés » mentirait.
3. **État d'une synchro à plusieurs paquets :** chaque commit pose
   `etat='terminee'` et `fin=maintenant` ; le paquet suivant les réécrit. Le
   serveur ne peut pas savoir quel paquet est le dernier, et un état
   « en cours » qui ne se fermerait jamais serait pire.
4. **Les exemples « capturés sur un échange réel »** de `CONTRAT-APP.md`
   (issue #15) ne peuvent l'être qu'avec le téléphone : la tâche 8 les laisse
   à la recette, en le disant.

## Contraintes globales

- Documentation, commentaires et docstrings **en français** (le mainteneur
  débute en Python) ; messages de commit **sans accents**, passés par
  `git commit -F - <<'FIN'` (jamais `-m` avec des accents graves).
- Chaque test est validé **par mutation** : casser le code, vérifier que c'est
  bien ce test-là qui tombe, remettre.
- Tests serveur : `python3 -m pytest -q` (299 au départ). Tests app :
  `JAVA_HOME=~/outils/jdk17 ./gradlew -p android testDebugUnitTest` (258 au départ).
- Tout ce qui écrit dans le journal passe par `_journaliser` (tâche 3) :
  **une panne du journal ne doit JAMAIS faire échouer une route**, surtout pas
  un commit — elle empêcherait l'horizon d'avancer.
- Toute nouvelle route d'admin : `require_admin`, ajout à `ADRESSES_ADMIN`
  (`tests/test_app.py:303`), et `/docs`, `/redoc`, `/openapi.json` toujours 404.
- La réponse de `/sync/commit` garde **exactement** sa forme actuelle : l'app
  la lit comme un dictionnaire de nombres (`ClientServeur.commit`), et une liste
  de mouvements la gonflerait d'une entrée par fichier.
- Le dossier `INCOMING_DIR/_echecs` (quarantaine, issue #16) n'est **jamais**
  touché par la purge.

## Points d'attention de la relecture

1. **La purge ne doit jamais emporter la quarantaine `_echecs`** — la purger
   réintroduirait #16 avec un délai. Test à la tâche 4.
2. **Une session en cours de réception dans un sous-dossier** (`<session>/DCIM/Camera/`)
   ne rafraîchit PAS la date du dossier de session, seulement celle de
   `DCIM/Camera`. Le critère est la date la plus récente de TOUTE
   l'arborescence (fichiers `.partiel` compris). Test à la tâche 4.
3. **Une panne du journal (base verrouillée, disque plein, chemin illisible)**
   ne doit ni faire échouer le commit ni empêcher l'horizon d'avancer. Test à
   la tâche 3.
4. **Un nom de fichier venu du téléphone contenant `<script>`** doit s'afficher
   échappé dans les pages d'historique. Test à la tâche 6.
5. **La réponse du commit ne contient pas les mouvements.** Test à la tâche 3.

---

## Carte des fichiers

| Fichier | Rôle |
|---|---|
| `mediasort/catalog.py` | + `chemin_de(empreinte)` (destination d'un doublon) |
| `mediasort/sorter.py` | + compteur `ignored`, + consommateur `sur_mouvement` |
| `mediasort/cli.py` | affiche le compteur d'ignorés (issue #27) |
| `phototheque/journal.py` | **nouveau** — la base du journal, écriture et lecture |
| `phototheque/config.py` | + `JOURNAL_DB` |
| `phototheque/sessions.py` | + `purger_abandonnees`, `abandonner` |
| `phototheque/ingest.py` | transmet le consommateur au trieur |
| `phototheque/devices.py` | + `label(id)`, + rappel `sur_confirmation` dans `validate` |
| `phototheque/app.py` | commit, upload, abandon, démarrage, événements, pages |
| `phototheque/web.py` | rendu HTML des quatre pages + lien depuis l'admin |
| `android/.../reseau/Contrat.kt`, `ClientServeur.kt`, `synchro/Orchestrateur.kt` | envoi de `synchro` et `bilan_app` |
| `docs/CONTRAT-APP.md`, `docs/DEPLOIEMENT.md`, `CLAUDE.md` | documentation |

---

### Tâche 1 : le trieur rend ses mouvements et compte ce qu'il ignore (#27)

**Fichiers :**
- Modifier : `mediasort/catalog.py` (après `has_hash`, ligne ~43)
- Modifier : `mediasort/sorter.py` (`Report`, `sort_folder`)
- Modifier : `mediasort/cli.py:63-64`
- Tests : `tests/test_catalog.py`, `tests/test_sorter.py`, `tests/test_cli.py`

**Interfaces :**
- Produit : `Catalog.chemin_de(digest: str) -> str | None`
- Produit : `sort_folder(source, library, catalog, dry_run=True, sur_mouvement=None) -> Report`,
  où `sur_mouvement(m: dict)` reçoit
  `{"origine": str (relatif à source, posix), "taille": int | None,
  "empreinte": str | None, "issue": str, "destination": str | None,
  "detail": str | None}` avec `issue` dans
  `"range" | "a_trier" | "doublon" | "refuse" | "exclu" | "erreur"`.
- Produit : `Report.ignored: int` et la clé `"ignores"` dans `to_dict()`.
  **`Report` ne garde AUCUNE liste de mouvements.**

- [ ] **Étape 1 : tests qui échouent**

Dans `tests/test_catalog.py` :

```python
def test_chemin_de_rend_le_chemin_du_media_deja_range(tmp_path):
    from mediasort.catalog import Catalog
    cat = Catalog(tmp_path / "c.db")
    cat.add_media("abc", 10, "/biblio/Photos/2025/01 JANVIER/a.jpg", None, "nom")
    assert cat.chemin_de("abc") == "/biblio/Photos/2025/01 JANVIER/a.jpg"
    assert cat.chemin_de("inconnue") is None
```

Dans `tests/test_sorter.py` (réutiliser les aides existantes du fichier pour
créer une photo datée ; regarder comment les tests voisins fabriquent un JPEG
et un catalogue, et faire pareil) :

```python
def test_chaque_fichier_produit_un_mouvement(tmp_path):
    """Issue #30 : le détail fichier par fichier, perdu jusqu'ici."""
    # source contient : une photo datée par son nom, un doublon d'une photo
    # déjà au catalogue, un .txt, un fichier sous « WhatsApp Images/Sent ».
    ...  # préparation avec les aides du fichier
    vus = []
    rapport = sort_folder(source, biblio, cat, dry_run=False, sur_mouvement=vus.append)
    par_issue = {m["issue"]: m for m in vus}
    assert set(par_issue) == {"range", "doublon", "refuse", "exclu"}
    assert par_issue["range"]["destination"].startswith(str(biblio))
    assert par_issue["range"]["empreinte"]
    # Le doublon désigne le média DÉJÀ présent qui l'a fait écarter.
    assert par_issue["doublon"]["destination"] == chemin_deja_range
    assert par_issue["refuse"]["origine"] == "notes.txt"


def test_une_extension_inconnue_est_comptee(tmp_path):
    """Issue #27 : le trieur ignorait sans le moindre compteur."""
    source = tmp_path / "src"; source.mkdir()
    (source / "notes.txt").write_text("x")
    rapport = sort_folder(source, tmp_path / "b", Catalog(tmp_path / "c.db"))
    assert rapport.ignored == 1
    assert rapport.to_dict()["ignores"] == 1


def test_sans_consommateur_aucun_mouvement_n_est_retenu(tmp_path):
    """Spec §8.10 : 20 000 médias ne doivent pas tenir 20 000 dict en mémoire."""
    source = tmp_path / "src"; source.mkdir()
    for i in range(50):
        (source / f"n{i}.txt").write_text("x")
    rapport = sort_folder(source, tmp_path / "b", Catalog(tmp_path / "c.db"))
    assert not any(isinstance(v, list) and len(v) >= 50 for v in vars(rapport).values())
    assert "mouvements" not in rapport.to_dict()
```

Dans `tests/test_cli.py`, sur le modèle des tests existants du bilan :

```python
def test_le_bilan_affiche_les_fichiers_ignores(tmp_path, capsys):
    ...  # source avec un .txt, lancer main([...]) comme les tests voisins
    assert "1 ignorés (extension non gérée)" in capsys.readouterr().out
```

- [ ] **Étape 2 : lancer, constater l'échec**

Run : `python3 -m pytest -q tests/test_catalog.py tests/test_sorter.py tests/test_cli.py`
Attendu : échecs sur `chemin_de`, `sur_mouvement`, `ignored`.

- [ ] **Étape 3 : implémenter**

`mediasort/catalog.py` :

```python
    def chemin_de(self, digest: str):
        """Chemin du média déjà rangé sous cette empreinte, ou None.

        Sert au journal du serveur (issue #30) : pour un doublon, c'est la
        réponse à « pourquoi celle-là n'est pas arrivée ».
        """
        cur = self._cx.execute("SELECT chemin FROM medias WHERE empreinte=?", (digest,))
        ligne = cur.fetchone()
        return ligne[0] if ligne else None
```

`mediasort/sorter.py` : ajouter `ignored: int = 0` au `Report` (avec un
commentaire renvoyant à #27), `"ignores": self.ignored` dans `to_dict()`, et
dans `sort_folder` un paramètre `sur_mouvement=None` plus une fonction locale :

```python
    def noter(p: Path, issue: str, empreinte=None, destination=None, detail=None):
        """Transmet le sort d'un fichier au consommateur, s'il y en a un.

        Rien n'est retenu ici : sur un tri de 20 000 médias en ligne de
        commande, garder la liste jusqu'à la fin coûterait pour rien.
        """
        if sur_mouvement is None:
            return
        try:
            taille = p.stat().st_size
        except OSError:
            taille = None
        sur_mouvement({"origine": p.relative_to(source).as_posix(), "taille": taille,
                       "empreinte": empreinte,
                       "destination": str(destination) if destination else None,
                       "issue": issue, "detail": detail})
```

Appels (la taille doit être lue AVANT `p.unlink()`, donc `noter` avant le
`unlink` pour le cas rangé) :
- `mtype is None` → `report.ignored += 1; noter(p, "refuse", detail="extension non gérée")`
- `is_excluded` → `noter(p, "exclu")` (après `report.skipped += 1`)
- doublon → `noter(p, "doublon", empreinte, catalog.chemin_de(empreinte))`
- rangé (après `add_media`, avant `unlink`) →
  `noter(p, "range" if dr.date else "a_trier", empreinte_copiee, dest)`
- en simulation (`dry_run`, juste avant `continue`) → même appel avec
  `empreinte` (qui peut être None) et `dest`
- `echec(p, raison)` → y ajouter `noter(p, "erreur", detail=raison)`

`mediasort/cli.py` : ajouter `, {report.ignored} ignorés (extension non gérée)`
au bilan imprimé, avant « erreurs ».

- [ ] **Étape 4 : lancer, tout doit passer** — `python3 -m pytest -q` (suite complète).
- [ ] **Étape 5 : mutation** — retirer l'appel `noter(p, "doublon", ...)` : le
  test des mouvements doit tomber. Remettre.
- [ ] **Étape 6 : commit** (`feat(mediasort): mouvements par fichier et compteur d'ignores (#27, #30)`).

---

### Tâche 2 : le module `journal`

**Fichiers :**
- Créer : `phototheque/journal.py`
- Modifier : `phototheque/config.py` (+ `JOURNAL_DB`)
- Test : `tests/test_journal.py`

**Interfaces :**
- Produit : `config.JOURNAL_DB: Path` (défaut `~/phototheque_journal.db`,
  surchargeable par la variable d'environnement `JOURNAL_DB`)
- Produit : `class Journal(db_path)` avec :
  - `evenement(type: str, appareil: str | None = None, adresse: str | None = None, detail: str | None = None) -> None`
  - `ajouter_mouvement(session: str, m: dict) -> None` (dict de la tâche 1)
  - `noter_refus(session: str, origine: str, detail: str) -> None`
  - `enregistrer_commit(synchro: str, session: str, appareil: str, label: str | None, adresse: str | None, bilan: dict, bilan_app: dict | None) -> None`
  - `synchros(limite: int = 200) -> list[dict]` (plus récente d'abord)
  - `synchro(identifiant: str) -> dict | None`
  - `mouvements(synchro: str) -> list[dict]`
  - `rechercher(q: str, limite: int = 200) -> list[dict]` (mouvements dont
    l'origine contient `q`, ou dont l'empreinte vaut `q`, avec la date de leur synchro)
  - `evenements(limite: int = 500) -> list[dict]` (plus récent d'abord)

- [ ] **Étape 1 : tests qui échouent** (`tests/test_journal.py`)

```python
from phototheque.journal import Journal

BILAN = {"sorted": 2, "duplicates": 1, "to_triage": 0, "errors": 0,
         "ignores": 0, "octets_ranges": 300}


def test_trois_paquets_font_une_seule_synchro(tmp_path):
    """Spec §8.1 : le regroupement par identifiant de synchro fonctionne."""
    j = Journal(tmp_path / "j.db")
    for n in range(3):
        j.enregistrer_commit("s1", f"sess{n}", "tel", "Pixel", "192.168.1.18", BILAN, None)
    lignes = j.synchros()
    assert len(lignes) == 1
    assert lignes[0]["paquets"] == 3 and lignes[0]["ranges"] == 6
    assert lignes[0]["octets"] == 900 and lignes[0]["etat"] == "terminee"


def test_les_mouvements_sont_rattaches_a_leur_synchro(tmp_path):
    j = Journal(tmp_path / "j.db")
    j.ajouter_mouvement("sess0", {"origine": "DCIM/Camera/a.jpg", "taille": 1,
                                  "empreinte": "e1", "issue": "range",
                                  "destination": "/b/a.jpg", "detail": None})
    j.noter_refus("sess0", "DCIM/Camera/b.heic", "extension non prise en charge")
    j.enregistrer_commit("s1", "sess0", "tel", "Pixel", None, BILAN, None)
    issues = sorted(m["issue"] for m in j.mouvements("s1"))
    assert issues == ["range", "refuse"]
    assert j.synchros()[0]["refuses"] == 1


def test_le_label_est_une_copie(tmp_path):
    """Spec §8.5 : supprimer l'appareil ne doit pas effacer son histoire."""
    j = Journal(tmp_path / "j.db")
    j.enregistrer_commit("s1", "sess0", "tel", "Pixel de Ken", None, BILAN, None)
    assert j.synchro("s1")["label"] == "Pixel de Ken"


def test_le_bilan_de_l_application_est_retenu(tmp_path):
    j = Journal(tmp_path / "j.db")
    j.enregistrer_commit("s1", "sess0", "tel", None, None, BILAN,
                         {"envoyes": 3, "refuses": 0, "echecs": 2})
    assert j.synchro("s1")["app_echecs"] == 2


def test_la_recherche_trouve_par_nom_et_par_empreinte(tmp_path):
    j = Journal(tmp_path / "j.db")
    j.ajouter_mouvement("sess0", {"origine": "DCIM/Camera/IMG_1.jpg", "taille": 1,
                                  "empreinte": "abc", "issue": "range",
                                  "destination": "/b/IMG_1.jpg", "detail": None})
    j.enregistrer_commit("s1", "sess0", "tel", None, None, BILAN, None)
    assert len(j.rechercher("IMG_1")) == 1
    assert len(j.rechercher("abc")) == 1
    assert j.rechercher("%") == []      # un joker SQL ne doit pas tout ramener


def test_les_evenements_sont_rendus_du_plus_recent_au_plus_ancien(tmp_path):
    j = Journal(tmp_path / "j.db")
    j.evenement("demarrage")
    j.evenement("appairage", appareil="tel")
    assert [e["type"] for e in j.evenements()] == ["appairage", "demarrage"]
```

- [ ] **Étape 2 : lancer** — `python3 -m pytest -q tests/test_journal.py` → ImportError.

- [ ] **Étape 3 : implémenter** `phototheque/journal.py`, sur le modèle de
`DeviceStore` (connexion partagée `check_same_thread=False` + `threading.Lock`,
tables créées dans `__init__`) :

```python
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
"""


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")
```

Points précis :
- `enregistrer_commit` : `INSERT OR IGNORE` de la ligne (`debut=maintenant`,
  `etat='en cours'`), puis rattachement des mouvements de `session`, puis
  `UPDATE` cumulatif :
  `paquets+1`, `ranges += sorted`, `a_trier += to_triage`, `doublons += duplicates`,
  `erreurs += errors`, `octets += octets_ranges`,
  `refuses += ignores + (nombre de mouvements 'refuse' de cette session)`,
  `envoyes += sorted + to_triage + duplicates + errors + ignores`,
  `app_echecs = bilan_app["echecs"]` si `bilan_app` (le téléphone envoie un
  cumul : on écrase), `fin=maintenant`, `etat='terminee'`, et `label` /
  `adresse` réécrits s'ils sont fournis. Utiliser `bilan.get(clé, 0)` partout :
  un vieux bilan sans `ignores` ne doit pas lever.
- `rechercher` : `origine LIKE ? ESCAPE '\'` avec `%`, `_` et `\` échappés dans
  `q`, **ou** `empreinte = ?` ; jointure gauche sur `synchros` pour la date.
- Lignes rendues en `dict` (`sqlite3.Row` → `dict(row)`).

- [ ] **Étape 4 : lancer** — `python3 -m pytest -q` (suite complète).
- [ ] **Étape 5 : mutation** — retirer `paquets+1` du UPDATE : le test des trois
  paquets tombe. Retirer l'échappement de `%` : le test de recherche tombe.
- [ ] **Étape 6 : commit** (`feat(serveur): base du journal (#30)`).

---

### Tâche 3 : le commit et l'upload écrivent dans le journal

**Fichiers :**
- Modifier : `phototheque/ingest.py` (`sort_session`)
- Modifier : `phototheque/devices.py` (+ `label`)
- Modifier : `phototheque/app.py` (`journal()`, `_journaliser`, `CommitRequest`,
  `sync_commit`, `sync_upload`)
- Test : `tests/test_app.py` (et le `_client` des tests pose `JOURNAL_DB`)

**Interfaces :**
- Consomme : `Journal` (tâche 2), `sort_folder(..., sur_mouvement=)` (tâche 1)
- Produit : `app.journal() -> Journal` (ouverture paresseuse, comme `devices()`)
- Produit : `app._journaliser(action: Callable[[Journal], None]) -> None` —
  exécute `action(journal())` et **avale toute exception** en la consignant
  par `logging` (`logging.getLogger("phototheque.journal").exception(...)`)
- Produit : `ingest.sort_session(session_dir, library, catalog, sur_mouvement=None) -> dict`
- Produit : `DeviceStore.label(device_id: str) -> str | None`
- Produit : `CommitRequest.synchro: str | None = None`,
  `CommitRequest.bilan_app: BilanApp | None = None` avec
  `class BilanApp(BaseModel): envoyes: int = 0; refuses: int = 0; echecs: int = 0`

- [ ] **Étape 1 : tests qui échouent** (dans `tests/test_app.py` ; ajouter
`monkeypatch.setenv("JOURNAL_DB", str(tmp_path / "journal.db"))` à `_client`
et `_client_depuis`, et regarder comment les tests existants appairent un
appareil et font un commit — les réutiliser)

```python
def test_un_commit_sans_identifiant_de_synchro_fait_une_ligne(tmp_path, monkeypatch):
    """Spec §8.2 : un téléphone qui n'envoie pas `synchro` reste journalisé."""
    ...  # appareil appairé, commit d'une session vide sans champ synchro
    lignes = a.journal().synchros()
    assert len(lignes) == 1 and lignes[0]["appareil"] == dev_id


def test_deux_commits_de_la_meme_synchro_font_une_ligne(tmp_path, monkeypatch):
    ...  # deux commits avec {"synchro": "abc123", ...}
    assert len(a.journal().synchros()) == 1
    assert a.journal().synchros()[0]["paquets"] == 2


def test_la_reponse_du_commit_ne_contient_pas_les_mouvements(tmp_path, monkeypatch):
    """L'app lit la réponse comme un dictionnaire de nombres."""
    ...  # envoyer une photo, commit
    assert "mouvements" not in r.json()


def test_un_journal_en_panne_ne_fait_pas_echouer_le_commit(tmp_path, monkeypatch):
    """Point d'attention 3 : l'horizon doit avancer quand même."""
    monkeypatch.setenv("JOURNAL_DB", str(tmp_path / "absent" / "sous" / "j.db"))
    ...  # _client APRÈS ce setenv ; commit avec horizons={"DCIM/Camera": 1.0e9}
    assert r.status_code == 200
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1.0e9}


def test_une_extension_refusee_a_l_envoi_est_journalisee(tmp_path, monkeypatch):
    ...  # upload de « notes.txt » → 400 ; puis commit de la même session
    assert [m["issue"] for m in a.journal().mouvements(synchro_id)] == ["refuse"]


def test_un_identifiant_de_synchro_hors_norme_est_remplace(tmp_path, monkeypatch):
    ...  # commit avec {"synchro": "x" * 500}
    assert len(a.journal().synchros()[0]["id"]) <= 64
```

- [ ] **Étape 2 : lancer** — échecs attendus (`journal` absent, champ inconnu ignoré…).

- [ ] **Étape 3 : implémenter**

`ingest.sort_session` passe `sur_mouvement` à `sort_folder`.
`DeviceStore.label` : `SELECT label FROM devices WHERE id=?`.

Dans `app.py` :

```python
_journal_ouvert = None


def journal() -> Journal:
    """Ouvre le journal à la PREMIÈRE UTILISATION (voir devices())."""
    global _journal_ouvert
    if _journal_ouvert is None:
        _journal_ouvert = Journal(config.JOURNAL_DB)
    return _journal_ouvert


_log_journal = logging.getLogger("phototheque.journal")


def _journaliser(action) -> None:
    """Écrit dans le journal sans JAMAIS faire échouer la route appelante.

    Un journal en panne (base verrouillée, disque plein) qui ferait échouer
    un commit empêcherait l'horizon d'avancer : le téléphone renverrait tout,
    indéfiniment, pour une simple trace. La trace passe après le travail.
    """
    try:
        action(journal())
    except Exception:
        _log_journal.exception("écriture du journal impossible")
```

Identifiant de synchro : accepté s'il fait 1 à 64 caractères de
`[A-Za-z0-9_-]` (motif compilé en tête de module), sinon remplacé par
`sessions.new_session()`. `sync_commit` prend `request: Request` pour
l'adresse (`request.client.host`). Le consommateur passé au tri :
`lambda m: _journaliser(lambda j: j.ajouter_mouvement(req.session, m))`.
Après le tri et la quarantaine :
`_journaliser(lambda j: j.enregistrer_commit(synchro, req.session, dev_id, devices().label(dev_id), adresse, bilan, req.bilan_app.model_dump() if req.bilan_app else None))`.

Dans `sync_upload`, sur refus d'extension, **si** `sessions.identifiant_valide(session)` :
`_journaliser(lambda j: j.noter_refus(session, path, detail))` avant le `raise`.

- [ ] **Étape 4 : lancer** — `python3 -m pytest -q`.
- [ ] **Étape 5 : mutation** — retirer le `try/except` de `_journaliser` : le
  test du journal en panne tombe. Remettre.
- [ ] **Étape 6 : commit** (`feat(serveur): le commit et l'upload alimentent le journal (#30)`).

---

### Tâche 4 : purge des sessions abandonnées et `POST /sync/abandon`

**Fichiers :**
- Modifier : `phototheque/sessions.py`
- Modifier : `phototheque/app.py` (route, démarrage via `lifespan`, purge après commit)
- Tests : `tests/test_sessions.py`, `tests/test_app.py`

**Interfaces :**
- Produit : `sessions.purger_abandonnees(base: Path, age_max_s: float = 24 * 3600, maintenant: float | None = None) -> list[dict]`
  — chaque élément `{"session": str, "fichiers": int, "octets": int}`
- Produit : `sessions.abandonner(base: Path, session: str) -> dict` —
  `{"supprimes": int, "octets": int}` ; lève `ValueError` si l'identifiant est hors norme
- Produit : `POST /sync/abandon` corps `{"session": "<32 hex>"}` → `200 {"supprimes", "octets"}`,
  `400` si identifiant hors norme ; `require_device`
- Produit : `app._purger()` — purge + un événement `purge` par session emportée

- [ ] **Étape 1 : tests qui échouent** (`tests/test_sessions.py`)

```python
import os, time
from phototheque import sessions


def _vieillir(chemin, secondes):
    t = time.time() - secondes
    for p in [chemin, *chemin.rglob("*")]:
        os.utime(p, (t, t))


def test_une_session_de_25_heures_est_purgee_une_recente_survit(tmp_path):
    """Spec §8.6."""
    vieille = tmp_path / ("a" * 32); (vieille / "DCIM").mkdir(parents=True)
    (vieille / "DCIM" / "x.jpg").write_bytes(b"123")
    recente = tmp_path / ("b" * 32); recente.mkdir(); (recente / "y.jpg").write_bytes(b"1")
    _vieillir(vieille, 25 * 3600); _vieillir(recente, 60)
    emportees = sessions.purger_abandonnees(tmp_path)
    assert [e["session"] for e in emportees] == ["a" * 32]
    assert emportees[0]["fichiers"] == 1 and emportees[0]["octets"] == 3
    assert not vieille.exists() and recente.exists()


def test_la_quarantaine_n_est_jamais_purgee(tmp_path):
    """Point d'attention 1 : purger _echecs réintroduirait l'issue #16."""
    abri = tmp_path / "_echecs" / "DCIM"; abri.mkdir(parents=True)
    (abri / "z.jpg").write_bytes(b"1")
    _vieillir(tmp_path / "_echecs", 400 * 24 * 3600)
    assert sessions.purger_abandonnees(tmp_path) == []
    assert (abri / "z.jpg").exists()


def test_une_reception_en_cours_dans_un_sous_dossier_protege_la_session(tmp_path):
    """Point d'attention 2 : la date du dossier de session ne bouge pas quand
    un fichier arrive dans un sous-dossier — seule celle du sous-dossier."""
    s = tmp_path / ("c" * 32); (s / "DCIM" / "Camera").mkdir(parents=True)
    (s / "DCIM" / "Camera" / "v.mp4.partiel").write_bytes(b"1")
    _vieillir(s, 30 * 3600)
    os.utime(s / "DCIM" / "Camera" / "v.mp4.partiel")     # écrit à l'instant
    assert sessions.purger_abandonnees(tmp_path) == []


def test_abandonner_refuse_un_identifiant_hors_norme(tmp_path):
    """Spec §8.7 : `..` ne doit rien supprimer du tout."""
    voisin = tmp_path / "voisin"; voisin.mkdir(); (voisin / "garde.jpg").write_bytes(b"1")
    base = tmp_path / "incoming"; base.mkdir()
    import pytest
    with pytest.raises(ValueError):
        sessions.abandonner(base, "../voisin")
    assert (voisin / "garde.jpg").exists()


def test_abandonner_rend_ce_qui_a_ete_supprime(tmp_path):
    s = tmp_path / ("d" * 32); s.mkdir(); (s / "a.jpg").write_bytes(b"12345")
    assert sessions.abandonner(tmp_path, "d" * 32) == {"supprimes": 1, "octets": 5}
    assert not s.exists()
```

Dans `tests/test_app.py` :

```python
def test_sync_abandon_exige_un_appareil(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    assert client.post("/sync/abandon", json={"session": "a" * 32}).status_code == 401


def test_le_demarrage_purge_et_se_journalise(tmp_path, monkeypatch):
    ...  # créer INCOMING_DIR/<32 hex> vieilli de 25 h AVANT le _client
    with TestClient(a.app):            # le `with` déclenche le lifespan
        pass
    types = [e["type"] for e in a.journal().evenements()]
    assert "demarrage" in types and "purge" in types
```

- [ ] **Étape 2 : lancer** — échecs attendus.

- [ ] **Étape 3 : implémenter**

`purger_abandonnees` : parcourir `base.iterdir()` ; ne considérer QUE les
dossiers dont le nom passe `identifiant_valide` (c'est ce qui écarte `_echecs`
par construction — le dire en commentaire) ; âge = `maintenant` moins le plus
grand `st_mtime` du dossier et de tout ce qu'il contient (`rglob("*")`) ;
au-delà de `age_max_s`, compter fichiers et octets puis `shutil.rmtree`.
Base absente → `[]`.

`abandonner` : `_verifier_session(session)` EN PREMIER, puis compter, puis
`cleanup`.

`app.py` : `FastAPI(..., lifespan=_cycle_de_vie)` avec

```python
from contextlib import asynccontextmanager


@asynccontextmanager
async def _cycle_de_vie(_app):
    """Au démarrage : trace + purge des sessions abandonnées (spec §5).

    Pas de tâche planifiée à installer ni à surveiller : le service purge en
    s'ouvrant et après chaque commit. Une purge qui échoue ne doit pas
    empêcher le service de démarrer.
    """
    _journaliser(lambda j: j.evenement("demarrage"))
    try:
        _purger()
    except OSError:
        _log_journal.exception("purge au démarrage impossible")
    yield
```

(le `FastAPI(...)` est créé en tête de module : définir `_cycle_de_vie`,
`_journaliser` et `_purger` AVANT lui, ou passer par
`app.router.lifespan_context = _cycle_de_vie` après leur définition.)
`_purger()` appelle `sessions.purger_abandonnees(config.INCOMING_DIR)` et
journalise un `evenement("purge", detail=f"session {e['session']} : {e['fichiers']} fichier(s), {e['octets']} octets")`
par élément. Appel aussi à la fin de `sync_commit` (dans un `try/except OSError`).
Route `sync_abandon` : `ValueError` → 400 ; journaliser `evenement("abandon", appareil=dev_id, detail=...)`.

- [ ] **Étape 4 : lancer** — `python3 -m pytest -q`.
- [ ] **Étape 5 : mutation** — retirer le filtre `identifiant_valide` : le test
  de la quarantaine tombe. Remplacer l'âge « arborescence » par le seul
  `st_mtime` du dossier de session : le test du sous-dossier tombe.
- [ ] **Étape 6 : commit** (`feat(serveur): purge des sessions abandonnees et /sync/abandon (#30)`).

---

### Tâche 5 : les événements (appairage, confirmation, révocation, échec d'authentification)

**Fichiers :**
- Modifier : `phototheque/devices.py` (`validate` gagne `sur_confirmation`)
- Modifier : `phototheque/app.py` (`require_device`, `require_admin`,
  `_assurer_appairage_en_cours`, `revoke_device`, `sync_desappairer`)
- Tests : `tests/test_devices.py`, `tests/test_app.py`

**Interfaces :**
- Produit : `DeviceStore.validate(secret, delai_minutes=..., sur_confirmation=None)` —
  `sur_confirmation(dev_id)` appelé UNE fois, au moment où un appairage en
  attente est confirmé, jamais ensuite
- `require_device` prend `request: Request` (adresse de l'événement)

- [ ] **Étape 1 : tests qui échouent**

```python
# tests/test_devices.py
def test_la_confirmation_est_signalee_une_seule_fois(tmp_path):
    store = DeviceStore(tmp_path / "d.db")
    dev_id, secret = store.pair("Pixel")
    vus = []
    store.validate(secret, sur_confirmation=vus.append)
    store.validate(secret, sur_confirmation=vus.append)
    assert vus == [dev_id]
```

```python
# tests/test_app.py
def test_une_requete_sans_identifiants_n_est_pas_un_echec_journalise(tmp_path, monkeypatch):
    """Spec §8.9 : le navigateur en envoie toujours une avant sa fenêtre."""
    _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/")
    assert all(e["type"] != "auth_echec" for e in a.journal().evenements())


def test_un_mauvais_mot_de_passe_est_journalise(tmp_path, monkeypatch):
    _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/", headers=_entetes("admin", "faux"))
    assert any(e["type"] == "auth_echec" for e in a.journal().evenements())


def test_appairage_confirmation_et_revocation_sont_journalises(tmp_path, monkeypatch):
    ...  # GET /pair (admin), utiliser le secret sur /sync/horizon, puis
    ...  # POST /devices/{id}/revoke (admin)
    types = [e["type"] for e in a.journal().evenements()]
    assert {"appairage", "confirmation", "revocation"} <= set(types)
```

- [ ] **Étape 2 : lancer** — échecs attendus.
- [ ] **Étape 3 : implémenter** — dans `validate`, appeler `sur_confirmation(dev_id)`
  APRÈS le `commit()` de la confirmation et HORS du verrou (un rappel qui
  reprendrait le verrou se bloquerait). Dans `require_admin`, le
  `_journaliser(... "auth_echec" ...)` va dans la branche
  `utilisateur != attendu or not verifier(...)` — et SEULEMENT là (pas dans
  la branche « pas d'en-tête Basic »), avec `adresse=source` et
  `detail=f"utilisateur « {utilisateur} »"`. `revoke_device` journalise
  `revocation` (`detail="depuis l'administration"`), `sync_desappairer`
  `revocation` (`detail="demandée par le téléphone"`), et
  `_assurer_appairage_en_cours` `appairage` quand il crée un appairage neuf.
- [ ] **Étape 4 : lancer** — `python3 -m pytest -q`.
- [ ] **Étape 5 : mutation** — déplacer l'événement `auth_echec` dans la branche
  « pas d'en-tête » : le test §8.9 tombe.
- [ ] **Étape 6 : commit** (`feat(serveur): evenements d'appairage, de revocation et d'authentification (#30)`).

---

### Tâche 6 : les quatre pages d'administration

**Fichiers :**
- Modifier : `phototheque/web.py` (+ `historique_html`, `synchro_html`,
  `recherche_html`, `evenements_html`, lien dans `admin_html`)
- Modifier : `phototheque/app.py` (4 routes GET)
- Test : `tests/test_app.py`

**Interfaces :**
- Consomme : `journal().synchros()`, `.synchro(id)`, `.mouvements(id)`,
  `.rechercher(q)`, `.evenements()` (tâche 2)
- Produit : routes `GET /historique`, `GET /historique/recherche?q=`,
  `GET /historique/{identifiant}` (404 si inconnu), `GET /evenements` —
  **`/historique/recherche` déclarée AVANT `/historique/{identifiant}`**, sinon
  FastAPI prend « recherche » pour un identifiant.

- [ ] **Étape 1 : tests qui échouent**

```python
ADRESSES_ADMIN = ["/", "/pair", "/devices", "/apk",
                  "/historique", "/historique/recherche?q=a", "/historique/x",
                  "/evenements"]
```

(remplacer la liste de `tests/test_app.py:303` : le test paramétré existant
vérifie alors les 401 des quatre nouvelles routes.)

```python
@pytest.mark.parametrize("adresse", ["/docs", "/redoc", "/openapi.json"])
def test_la_documentation_reste_fermee(adresse, tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    assert client.get(adresse).status_code == 404


def test_un_nom_de_fichier_hostile_est_echappe(tmp_path, monkeypatch):
    """Point d'attention 4 : le nom vient du téléphone."""
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    a.journal().ajouter_mouvement("sess0", {
        "origine": "DCIM/<script>alert(1)</script>.jpg", "taille": 1,
        "empreinte": "e", "issue": "range", "destination": "/b/x.jpg", "detail": None})
    a.journal().enregistrer_commit("s1", "sess0", "tel", "Pixel", None, {}, None)
    for adresse in ["/historique/s1", "/historique/recherche?q=script"]:
        texte = client.get(adresse, headers=entetes).text
        assert "<script>alert" not in texte and "&lt;script&gt;" in texte


def test_l_historique_montre_les_synchros_et_l_admin_y_mene(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    a.journal().enregistrer_commit("s1", "sess0", "tel", "Pixel", "192.168.1.18",
                                   {"sorted": 4}, None)
    assert "Pixel" in client.get("/historique", headers=entetes).text
    assert 'href="/historique"' in client.get("/", headers=entetes).text
    assert client.get("/historique/inconnue", headers=entetes).status_code == 404
```

- [ ] **Étape 2 : lancer** — échecs attendus.
- [ ] **Étape 3 : implémenter** — même gabarit que les pages existantes de
  `web.py` (thème clair/sombre, `html.escape` sur **chaque** valeur venue de la
  base ou de la requête, `q` compris). `/historique` : une ligne par synchro,
  « vert » si `erreurs == 0` et (`app_echecs` nul ou 0), sinon « rouge », **avec
  un mot** et pas seulement une couleur (règle d'accessibilité déjà suivie par
  `admin_html`). `/historique/{id}` : ses mouvements, origine → destination.
  `/evenements` : date, type, appareil, adresse, détail.
- [ ] **Étape 4 : lancer** — `python3 -m pytest -q`.
- [ ] **Étape 5 : mutation** — retirer un `html.escape` sur l'origine : le test
  d'échappement tombe. Inverser l'ordre des deux routes `/historique/...` : le
  test de la recherche tombe.
- [ ] **Étape 6 : commit** (`feat(serveur): pages d'historique et d'evenements (#30)`).

---

### Tâche 7 : l'application envoie `synchro` et `bilan_app`

**Fichiers :**
- Modifier : `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Contrat.kt:53`
- Modifier : `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/ClientServeur.kt:174`
- Modifier : `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Orchestrateur.kt`
  (interface `Serveur`, appel à `commit`, adaptateur de `Decouverte.kt`)
- Tests : `android/app/src/test/.../synchro/OrchestrateurTest.kt`, test du contrat existant

**Interfaces :**
- Produit : `@Serializable data class BilanApp(val envoyes: Int, val refuses: Int, val echecs: Int)`
- Produit : `RequeteCommit(session, horizons, synchro: String? = null, @SerialName("bilan_app") bilanApp: BilanApp? = null)`
- Produit : `Serveur.commit(session: String, horizons: Map<String, Double>, synchro: String, bilanApp: BilanApp): Map<String, Double>`

- [ ] **Étape 1 : tests qui échouent** — `FauxServeur` (dans `OrchestrateurTest`)
  enregistre les `synchro` et `bilanApp` reçus.

```kotlin
@Test fun tous_les_paquets_d_une_synchro_portent_le_meme_identifiant() {
    // Issue #30 : c'est lui qui regroupe N commits en UNE ligne d'historique.
    ...  // assez de médias pour 3 paquets (taillePaquet réduite, cf. tests voisins)
    assertEquals(1, serveur.synchrosRecues.toSet().size)
    assertEquals(3, serveur.synchrosRecues.size)
}

@Test fun deux_synchronisations_ont_deux_identifiants() { ... }

@Test fun le_bilan_app_envoye_est_cumule() {
    // Le dernier commit porte les comptes de TOUTE la synchro, pas du seul paquet.
    ...
}
```

  Et dans le test de contrat existant : la sérialisation de `RequeteCommit`
  contient `"synchro"` et `"bilan_app"` (snake_case, comme le serveur l'attend).

- [ ] **Étape 2 : lancer** —
  `JAVA_HOME=~/outils/jdk17 ./gradlew -p android testDebugUnitTest` → échec de compilation.
- [ ] **Étape 3 : implémenter** — l'identifiant est engendré UNE fois par appel
  à `Orchestrateur.synchroniser` (`java.util.UUID.randomUUID().toString().replace("-", "")`,
  32 caractères, compatible avec le motif du serveur) ; chaque commit envoie
  `BilanApp(envoyes, refuses, echecs)` cumulés à cet instant.
- [ ] **Étape 4 : lancer** — suite app complète, puis `assembleDebug`.
- [ ] **Étape 5 : mutation** — engendrer l'identifiant dans la boucle des
  paquets : le premier test tombe.
- [ ] **Étape 6 : commit** (`feat(app): chaque commit porte son identifiant de synchro et le bilan du telephone (#30)`).

---

### Tâche 8 : documentation

**Fichiers :** `docs/CONTRAT-APP.md`, `docs/DEPLOIEMENT.md`, `CLAUDE.md`

- [ ] `CONTRAT-APP.md` : les deux champs optionnels du commit (tableau de la
  spec §6), la route `POST /sync/abandon` (corps, réponse, 400, `require_device`,
  « au mieux, échec ignoré, la purge de 24 h est le filet »). Signaler en clair
  que les exemples **capturés sur un échange réel** restent à faire à la
  prochaine recette sur téléphone.
- [ ] `DEPLOIEMENT.md` : l'existence de `~/phototheque_journal.db` (créée au
  premier usage, à inclure dans toute sauvegarde du NUC), la purge des
  sessions de plus de 24 h au démarrage et après chaque commit, les quatre pages.
- [ ] `CLAUDE.md` : l'état (journal livré, #27 réglée), et un piège : **la
  quarantaine `_echecs` vit dans `INCOMING_DIR`, toute purge doit l'écarter**.
- [ ] Commit (`docs: journal serveur et sessions abandonnees (#30, #27)`).

---

## Recette (après déploiement sur le NUC)

À faire avec le téléphone, en même temps que la suite de la recette du lot 2 :
une sauvegarde réelle, puis `/historique` doit montrer UNE ligne, `/historique/<id>`
les destinations, une recherche par nom retrouver une photo, et `/evenements`
le démarrage du service. Capturer à cette occasion les exemples réels de
`CONTRAT-APP.md`.
