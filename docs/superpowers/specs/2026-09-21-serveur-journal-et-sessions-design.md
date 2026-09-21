# Lot serveur — journal consultable et sessions abandonnées

**Date :** 2026-09-21 · **État :** conception validée · **Va avec :**
[`2026-09-21-app-android-lot1bis-synchro-observable-design.md`](2026-09-21-app-android-lot1bis-synchro-observable-design.md)

---

## 1. Le besoin

Le 2026-09-21, la première synchronisation depuis un vrai téléphone a envoyé 971
fichiers et 14 Go. Elle s'est parfaitement rangée. Mais :

- **le téléphone ne l'a jamais su** — son délai d'expiration de 10 s a coupé
  pendant que le serveur triait ;
- **le serveur ne s'en souvient pas** — rien, nulle part, ne dit qu'une
  synchronisation a eu lieu.

Vérifié après coup, et pire que prévu : ce commit-là n'apparaît **même pas
dans `journalctl`**. uvicorn journalise une requête au moment où il y répond ;
le client ayant raccroché, la ligne n'a jamais été écrite. Le travail, lui, a
bien eu lieu — 953 médias rangés, horizons avancés, dépôt vidé — en 1 h 02 min
dont il ne reste aucune trace. `grep sync/commit` sur le journal ne prouve
donc strictement rien, et c'est précisément le trou que ce lot comble.

Ces deux faits se répondent. Quand le téléphone perd la réponse, le serveur doit
pouvoir la donner. Aujourd'hui il ne le peut pas : le catalogue connaît les
empreintes, la base des appareils connaît les horizons, et `journalctl` n'a que
des lignes HTTP qu'il finit par effacer.

Le code l'admet lui-même. Dans `app.py`, quand un horizon aberrant est écarté :

> « On ignore le dossier fautif plutôt que de rejeter tout l'envoi […]
> **Silencieusement, faute de journal dans ce module.** »

Demande du mainteneur, mot pour mot :

> « depuis l'interface web sous accès admin je veux aussi pouvoir voir un
> historique de tout ce qui s'est passé — connexion / id téléphone / date /
> fichiers envoyés / échecs / fichiers triés / emplacements etc. »

Second besoin, découvert le même jour : **une session abandonnée n'est jamais
nettoyée**. `sessions.cleanup()` n'est appelé qu'au `commit`. Une synchronisation
tuée en plein vol laisse son dossier dans `Famille/incoming/` indéfiniment —
plusieurs gigaoctets invisibles, que rien ne rangera ni n'effacera jamais.

## 2. Décisions prises, et pourquoi

| Décision | Choix | Raison |
|---|---|---|
| Où vivent les traces | **Nouvelle base `~/phototheque_journal.db`** | Le catalogue appartient au trieur en ligne de commande, partagé avec `python3 -m mediasort`. La base des appareils est minuscule et sensible. Un journal qui grossit n'a rien à faire dans l'une ou l'autre. |
| Granularité | **Une ligne par synchro, une ligne par fichier, une ligne par événement** | Les quatre questions posées par le mainteneur s'y rangent toutes. |
| Rétention | **Tout est gardé** | ~1 ligne par média. Le catalogue en compte 44 669 après deux ans de bibliothèque : SQLite ne bronchera pas. |
| Ce qui n'est pas rangé | **Journalisé aussi** | Doublons, `_A_TRIER`, extensions refusées : aujourd'hui ils ne laissent **aucune** trace. C'est précisément ce que le mainteneur veut voir. |
| Purge des sessions | **À l'ouverture du service et après chaque commit** | Pas de tâche planifiée à installer et à surveiller. |

## 3. Le stockage

`~/phototheque_journal.db`, trois tables.

### `synchros` — « est-ce que ça marche ? »

```sql
CREATE TABLE synchros (
  id           TEXT PRIMARY KEY,   -- fourni par l'app, sinon engendré
  appareil     TEXT NOT NULL,      -- id de la base des appareils
  label        TEXT,               -- son nom lisible, figé au moment des faits
  adresse      TEXT,               -- IP du téléphone
  debut        TEXT NOT NULL,
  fin          TEXT,               -- NULL tant qu'elle n'est pas finie
  paquets      INTEGER DEFAULT 0,
  envoyes      INTEGER DEFAULT 0,  -- reçus par le serveur
  ranges       INTEGER DEFAULT 0,
  doublons     INTEGER DEFAULT 0,
  a_trier      INTEGER DEFAULT 0,
  refuses      INTEGER DEFAULT 0,  -- extension non gérée
  erreurs      INTEGER DEFAULT 0,
  octets       INTEGER DEFAULT 0,
  app_echecs   INTEGER,            -- échecs côté téléphone, s'il les rapporte
  etat         TEXT NOT NULL       -- 'en cours' | 'terminee' | 'abandonnee'
);
```

`label` est **copié**, pas référencé : un appareil révoqué puis supprimé ne doit
pas effacer l'histoire de ce qu'il a envoyé.

### `mouvements` — « où est passée cette photo ? »

Une ligne par fichier traité, rangé **ou non**.

```sql
CREATE TABLE mouvements (
  id           INTEGER PRIMARY KEY,
  synchro      TEXT NOT NULL REFERENCES synchros(id),
  horodatage   TEXT NOT NULL,
  origine      TEXT NOT NULL,      -- 'DCIM/Camera/IMG_20250927_165346.jpg'
  taille       INTEGER,
  empreinte    TEXT,
  issue        TEXT NOT NULL,      -- 'range'|'doublon'|'a_trier'|'refuse'|'erreur'
  destination  TEXT,               -- 'Photos/2025/09 SEPTEMBRE/IMG_...jpg'
  detail       TEXT                -- le message d'erreur, le cas échéant
);
CREATE INDEX idx_mouvements_synchro  ON mouvements(synchro);
CREATE INDEX idx_mouvements_origine  ON mouvements(origine);
CREATE INDEX idx_mouvements_empreinte ON mouvements(empreinte);
```

Pour un doublon, `destination` porte le chemin du média **déjà présent** qui l'a
fait écarter : c'est la réponse à « pourquoi celle-là n'est pas arrivée ».

### `evenements` — « qui a touché au serveur ? »

```sql
CREATE TABLE evenements (
  id          INTEGER PRIMARY KEY,
  horodatage  TEXT NOT NULL,
  type        TEXT NOT NULL,   -- 'appairage'|'confirmation'|'revocation'
                               -- |'auth_echec'|'demarrage'|'purge'
  appareil    TEXT,
  adresse     TEXT,
  detail      TEXT
);
```

`auth_echec` mérite d'exister : la limitation d'essais de l'issue #19 compte les
échecs **en mémoire** et ne laisse aucune trace — un `systemctl restart` efface
tout. Attention toutefois à ne journaliser que les vrais échecs : une requête
**sans identifiants n'en est pas un**, le navigateur en envoie toujours une avant
d'afficher sa fenêtre de connexion.

La quatrième question du mainteneur — ce qui a changé dans la bibliothèque — se
calcule par agrégation de `mouvements`. Pas de table de plus.

## 4. Ce que le trieur doit rendre en plus

`mediasort.sorter.Report` (`sorter.py:14`) ne rend aujourd'hui que des
**compteurs** et deux agrégats. Le détail fichier par fichier n'existe nulle
part : il est perdu au fil du tri.

`Report` gagne donc une liste de mouvements — origine, taille, empreinte, issue,
destination —, et `to_dict()` la rend disponible. `sort_session()` la transmet à
`app.py`, qui l'écrit dans `mouvements`.

**C'est exactement ce que réclame l'issue #27.** Le trieur en ligne de commande
ignore les extensions qu'il ne sait pas ranger *sans le moindre compteur* :
l'utilisateur ne peut pas savoir qu'un fichier a été laissé de côté. La même
modification donne au serveur son journal et à la ligne de commande son compteur
manquant. Les deux se règlent d'un coup, et #27 se ferme avec ce lot.

Contrainte : sur un tri de 20 000 médias en ligne de commande, la liste ne doit
pas être tenue en mémoire jusqu'à la fin. `Report` reçoit un consommateur
optionnel appelé au fil de l'eau ; sans consommateur, seuls les compteurs sont
tenus, comme aujourd'hui.

## 5. Les sessions abandonnées

### Purge

Au démarrage du service et après chaque commit : tout dossier de
`INCOMING_DIR` dont la **date de modification** remonte à plus de 24 h est
supprimé, et un événement `purge` est journalisé avec ce qu'il contenait.

La date de modification du dossier est le bon critère : elle est rafraîchie à
chaque fichier reçu, donc une synchronisation en cours — même très longue — n'est
jamais purgée. 24 h laisse largement la place à une reprise automatique.

### `POST /sync/abandon`

L'arrêt immédiat décidé côté application laisse un paquet en cours dans le dépôt.
L'application prévient :

```
POST /sync/abandon     { "session": "<32 hex>" }
→ 200 { "supprimes": 12, "octets": 384102912 }
```

Authentifié comme appareil, exactement comme `commit`. L'identifiant de session
est vérifié par `sessions.identifiant_valide()` **avant** toute suppression — la
même précaution qu'au commit, et pour la même raison : cet identifiant devient un
nom de dossier, et le nettoyage supprime récursivement.

L'application tente cet appel au mieux et **ignore son échec** : si le réseau est
tombé, la purge des 24 h est le filet.

## 6. Le contrat de l'application

Deux champs **optionnels** s'ajoutent au corps de `POST /sync/commit`. Un
téléphone qui ne les envoie pas continue de fonctionner à l'identique.

| Champ | Type | Rôle |
|---|---|---|
| `synchro` | `str` | Identifiant engendré par le téléphone au début d'une synchronisation, répété à chaque paquet. C'est lui qui regroupe N commits en **une** ligne d'historique. Sans lui, le serveur en fabrique un par commit. |
| `bilan_app` | `{envoyes, refuses, echecs}` | Ce que le téléphone a vu de son côté. Les échecs de lecture locale et les coupures réseau sont **invisibles au serveur** : sans ce champ, la colonne « échecs » de l'historique serait toujours incomplète. |

`docs/CONTRAT-APP.md` est mis à jour en conséquence, avec des exemples **capturés
sur un échange réel** comme le veut l'usage établi par l'issue #15.

## 7. Les pages d'administration

Toutes derrière `require_admin`, comme le reste.

| Chemin | Contenu |
|---|---|
| `/historique` | Les synchronisations, la plus récente en haut : date, appareil, adresse, durée, envoyés / rangés / doublons / à trier / refusés / erreurs, volume. Vert ou rouge d'un coup d'œil. |
| `/historique/<id>` | Le détail d'une synchronisation : ses mouvements, avec pour chacun son origine sur le téléphone et sa destination dans la bibliothèque. |
| `/historique/recherche?q=` | Recherche d'un média par nom d'origine ou par empreinte, à travers toutes les synchronisations. C'est la réponse à « où est passée cette photo ». |
| `/evenements` | Appairages, révocations, échecs d'authentification, démarrages, purges. |

Un lien vers `/historique` est ajouté à la page d'administration existante.

> **⚠️ À chaque ajout de route, revérifier `/docs`, `/redoc` et `/openapi.json`.**
> FastAPI les publie **sans authentification** et ils n'apparaissent nulle part
> dans le code. Ils étaient ouverts sur le NUC jusqu'au 18/09. Ils sont
> aujourd'hui fermés (404), rouvrables par `DOCS_PUBLIQUES=1` en développement.
> Ce lot ajoute quatre routes : c'est le moment typique où la protection saute.

## 8. Stratégie de test

Validation **par mutation** systématique, comme sur tout le projet.

1. **Une synchronisation en trois paquets produit UNE ligne** dans `synchros`,
   pas trois — le regroupement par `synchro` fonctionne.
2. **Un commit sans champ `synchro`** (ancien téléphone) produit quand même une
   ligne cohérente.
3. **Un doublon est journalisé** avec le chemin du média déjà présent.
4. **Une extension refusée est journalisée** — et le compteur correspondant
   apparaît aussi en ligne de commande (issue #27).
5. **Un appareil supprimé ne fait pas disparaître son historique** : `label` est
   bien une copie.
6. **La purge n'emporte pas une session active** : un dossier touché il y a une
   minute survit, un dossier de 25 h disparaît.
7. **`/sync/abandon` refuse un identifiant hors norme** avant de supprimer quoi
   que ce soit — le test tente `..` et vérifie que le dossier voisin est intact.
8. **Les quatre nouvelles routes exigent l'authentification**, et `/docs` répond
   toujours 404.
9. **Une requête sans identifiants n'engendre pas d'événement `auth_echec`.**
10. **Un tri de 20 000 médias ne tient pas 20 000 mouvements en mémoire** quand
    aucun consommateur n'est fourni.

## 9. Hors périmètre

- **Les 44 669 médias déjà rangés n'ont pas de mouvements rétroactifs.**
  L'historique commence le jour de son installation. Le catalogue garde leur
  `chemin` et leur `date_import` ; c'est tout ce qu'on peut en dire honnêtement.
- **La revue visuelle des doublons** (issue #4) reste de la phase 2. Ce journal
  la préparera : il dira enfin quels doublons ont été écartés et au profit de quoi.
- **Toute exposition hors du LAN.** Rien ne change de ce côté.
