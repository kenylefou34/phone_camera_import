# Spec — Service d'ingestion + découverte réseau (Phase 1, sous-projet 2, v1)

*Rédigé le 2026-09-14. Document de conception, en français. Tout le code produit
sera commenté et documenté en français.*

---

## 1. Contexte et périmètre

Deuxième sous-projet de la refonte. Il fournit le **pont** entre le téléphone et
le trieur `mediasort` : un service sur le NUC qui **reçoit les médias poussés**
par le téléphone (sans jamais recevoir de doublon), les **range** via le trieur,
et se rend **trouvable tout seul** sur le réseau local.

**Dans le périmètre (v1) :** le serveur sur le NUC — appairage par QR, API de
synchronisation (plan/upload/commit avec **bilan détaillé**), **page web d'admin**
(appairage, liste/révocation des appareils, stats disque avec camembert),
découverte mDNS, service systemd, **reproduction (README + Docker)**, intégration
avec `mediasort` (dont enrichissement de son `Report`).

**Hors périmètre :** l'application Android (scanner de QR, scan des dossiers,
client d'upload) = **sous-projet 3** ; le tableau de bord web complet = **Phase 2**.

---

## 2. Décisions verrouillées (issues du brainstorming)

- **Architecture** : Approche A — serveur **FastAPI** (moderne, typé, doc auto),
  lancé par **systemd**, dépendances dans un **venv** dédié sur le NUC.
- **Sécurité / appairage** : **QR code**. Le NUC affiche une page web avec un QR
  encodant `{url stable (nuc.local), secret}` ; l'app le scanne et stocke le
  secret. Authentification par **jeton porteur (Bearer)** par appareil.
- **Anti-doublon** : **filtre par date** côté app (limite ce qu'il faut hacher)
  **+ poignée de main d'empreintes** côté NUC (le NUC répond « ce qui manque »),
  en réutilisant **directement le catalogue** `mediasort` (`has_hash`).
- **Déclenchement du tri** : **commit explicite** (b1). L'app appelle
  `/sync/commit` quand elle a fini d'uploader ; le NUC trie le lot d'un coup et
  renvoie un **bilan**.
- **Transport** : **HTTP** en v1 (le secret circule en clair sur le LAN). Passage
  à HTTPS + épinglage de certificat prévu → **issue #3** (le QR réserve déjà un
  champ `cert_sha256`).
- **Machine cible** : NUC `izquierdo@192.168.1.21`, Ubuntu 26.04, Python 3.14.
  Bibliothèque `Famille` sur `/media/izquierdo/Famille`, catalogue
  `~/mediasort_catalog.db`.

---

## 3. Architecture — nouveau paquet `mediaserve/`

Un module = une responsabilité, à côté de `mediasort/` (qu'il réutilise).

```
mediaserve/
  __init__.py
  config.py     # constantes : port, chemins (library, catalog, incoming, devices db)
  devices.py    # stockage/validation des jetons d'appareils (SQLite)
  pairing.py    # génération du QR (SVG) + charge utile d'appairage
  sessions.py   # gestion des sessions de synchro (dossiers incoming/<session>)
  stats.py      # stats disque (shutil.disk_usage) + médias (catalogue) + camembert SVG
  web.py        # page HTML d'admin (QR, liste appareils, stats + camembert)
  app.py        # application FastAPI : les endpoints + dépendance d'auth
  ingest.py     # intégration trieur : lance sort_folder sur une session, verrou
tests/
  test_devices.py test_pairing.py test_sessions.py test_stats.py test_app.py test_ingest.py
deploy/
  mediaserve.service          # unité systemd
  avahi-mediaserve.service    # service Avahi (mDNS)
  Dockerfile                  # image du service (reproduction Docker)
  docker-compose.yml          # montage volume médias + réseau hôte (mDNS)
requirements-server.txt        # fastapi, uvicorn, python-multipart, qrcode
```

Réutilise de `mediasort` : `Catalog` (has_hash, add_media), `sort_folder`,
`file_hash`. Aucune duplication de logique de tri.

---

## 4. Contrat d'API (le livrable clé — le sous-projet 3 le consommera)

Base : `http://nuc.local:8787`. Toutes les routes `/sync/*` et `/status`
exigent l'en-tête `Authorization: Bearer <secret>`.

### 4.1 Appairage
`GET /pair`
→ Page HTML affichant un **QR code (SVG)** qui encode ce JSON :
```json
{ "url": "http://nuc.local:8787", "token": "<secret opaque>", "cert_sha256": null }
```
À l'ouverture de la page, le NUC **génère un nouveau secret**, l'enregistre
(haché) comme appareil actif, et l'affiche dans le QR. Ouvrir `/pair` à nouveau
= appairer un autre téléphone (nouveau secret).

### 4.2 Plan de synchro (poignée de main d'empreintes)
`POST /sync/plan`
```json
// requête
{ "files": [ {"path": "Pictures/WhatsApp/IMG-20230526-WA0001.jpg",
              "size": 123456, "hash": "<sha256 hex>"}, ... ] }
// réponse
{ "session": "<id session>", "needed": ["<sha256>", "<sha256>", ...] }
```
Le NUC compare chaque `hash` au **catalogue** (`has_hash`) et renvoie **seulement
les empreintes qu'il n'a pas** (`needed`). L'app n'uploadera que ces fichiers-là.
`session` relie le plan, les uploads et le commit.

### 4.3 Upload des fichiers manquants
`POST /sync/upload` — `multipart/form-data`
- champs : `session`, `path` (chemin relatif d'origine), `file` (le contenu).
- Le NUC écrit dans `Famille/incoming/<session>/<path>` (**le chemin d'origine
  est préservé** pour que le trieur reclasse WhatsApp/Photos/Vidéos correctement),
  puis **revérifie l'empreinte** du fichier reçu.
```json
// réponse
{ "ok": true, "hash": "<sha256 vérifié>" }
```

### 4.4 Commit (déclenche le tri)
`POST /sync/commit`
```json
// requête
{ "session": "<id session>" }
// réponse (bilan DÉTAILLÉ du trieur)
{
  "sorted": 12, "duplicates": 3, "to_triage": 0, "skipped": 1, "errors": 0,
  "photos": 8, "videos": 4, "whatsapp": 5,
  "par_source_date": { "metadata": 2, "filename": 9, "filesystem": 1 },
  "octets_ranges": 123456789,
  "par_annee_mois": { "2023/05 MAI": 4, "2022/09 SEPTEMBRE": 8 }
}
```
Le NUC lance `sort_folder(incoming/<session>, library=Famille, catalog)`, range
dans Famille, **supprime** le dossier de session, et renvoie le bilan. **Un seul
tri à la fois** (verrou, voir §7).

> **Impact sur le sous-projet 1** : la structure `Report` de `mediasort.sorter`
> est **enrichie** de ces compteurs (photos, vidéos, whatsapp, par source de
> date, octets rangés, répartition année/mois). C'est une extension rétro-
> compatible (les 5 compteurs actuels restent), à faire en TDD dans `mediasort`.

### 4.5 Statut
`GET /status` → JSON avec l'état du service, du disque et de la bibliothèque :
```json
{
  "ok": true,
  "library": "/media/izquierdo/Famille",
  "catalog_count": 44669,
  "disque": { "total": 999999999999, "utilise": 666666666666,
              "libre": 333333333333, "pourcentage_utilise": 67 },
  "medias": { "photos": 40000, "videos": 4669 }
}
```
Sert notamment à l'app pour afficher l'**espace libre avant un upload**.

### 4.6 Gestion des appareils appairés
- `GET /devices` → liste des appareils appairés `[{ "id": "...", "label": "...",
  "paired_at": "..." }]`.
- `POST /devices/{id}/revoke` → révoque (supprime) le jeton de cet appareil.

### 4.7 Page web d'administration
`GET /` → petite page HTML d'admin (servie par le NUC) qui regroupe :
- le **QR d'appairage** (renvoi à `/pair`),
- la **liste des appareils appairés** avec un bouton **« Révoquer »** par appareil,
- les **stats disque** sous forme de **camembert SVG** (utilisé / libre), rendu
  **côté serveur** (aucune dépendance JS externe), + l'espace libre en clair,
- un résumé médias (photos / vidéos, total au catalogue).

Cette page reste une **page d'admin/état** minimale ; la consultation/revue
visuelle complète des médias reste la **Phase 2**.

---

## 5. Appairage & sécurité (v1)

- **Secret par appareil** : chaîne aléatoire opaque (ex. 32 octets base64url).
  Stocké **haché** (SHA-256) dans `devices` (SQLite), avec `label` et date. Le
  secret en clair n'existe que dans le QR et dans l'app.
- **Validation** : dépendance FastAPI qui lit l'en-tête `Authorization: Bearer`,
  hache et compare à `devices`. Sinon → `401`.
- **Révocation** : gérée depuis la **page web d'admin** (§4.7) — liste des
  appareils appairés + bouton « Révoquer » (appelle `POST /devices/{id}/revoke`).
- **HTTP v1** : acceptable sur LAN de confiance ; le secret transite en clair.
  Durcissement (HTTPS + `cert_sha256` épinglé dans le QR) → **issue #3**.

---

## 6. Découverte mDNS/Avahi

- Fichier de service Avahi `deploy/avahi-mediaserve.service` (déposé dans
  `/etc/avahi/services/`) qui annonce le type **`_mediaserve._tcp`** sur le port
  **8787**. Avahi est déjà présent sur le NUC.
- L'app **parcourt** `_mediaserve._tcp` → obtient l'hôte (`nuc.local`) + le port.
  Le QR fournit le secret. La résolution de `nuc.local` par mDNS rend l'adresse
  **stable malgré les changements d'IP (DHCP)**.

---

## 7. Intégration avec le trieur

- Les fichiers reçus atterrissent dans **`Famille/incoming/<session>/`** (même
  disque que la bibliothèque → le tri est un déplacement same-fs, rapide).
- Le chemin d'origine est **préservé** (`incoming/<session>/Pictures/WhatsApp/…`)
  pour que la détection WhatsApp et le type (photo/vidéo) du trieur fonctionnent.
- `ingest.py` lance `sort_folder(...)` avec le **catalogue partagé**
  `~/mediasort_catalog.db` (donc dédoublonnage cohérent avec le reste).
- **Verrou de tri** : un seul `sort_folder` à la fois (verrou en mémoire dans le
  process serveur), pour éviter deux commits concurrents.
- Après le tri : suppression du dossier `incoming/<session>/`.

---

## 8. Déploiement

- **Dépendances** (venv dédié sur le NUC) : `fastapi`, `uvicorn[standard]`,
  `python-multipart`, `qrcode` (rendu **SVG**, donc pas besoin de Pillow).
- **Lancement** : `uvicorn mediaserve.app:app --host 0.0.0.0 --port 8787`.
- **systemd** : unité `deploy/mediaserve.service`, `User=izquierdo`,
  `Restart=on-failure`, démarrage au boot.
- ⚠️ **Point de vigilance** : les disques sont montés sous `/media/izquierdo` par
  la session de bureau (udisks). Le service doit démarrer **après** que les
  disques soient montés (dépendance systemd sur le point de montage, ou service
  utilisateur `systemctl --user` avec *lingering*). À valider à l'implémentation.

### 8.1 Reproduction sur une autre machine (README)
Le **README** décrira, en français, comment **dupliquer le système** :
- **Machine Linux « classique »** : cloner le dépôt, créer le venv serveur,
  installer les dépendances, régler les chemins (bibliothèque, catalogue), poser
  le service systemd + le service Avahi, démarrer.
- **Docker** (`deploy/Dockerfile` + `deploy/docker-compose.yml`) : image
  contenant le service ; on **monte le dossier médias en volume** et on utilise
  le **réseau hôte** (`network_mode: host`) pour que le mDNS/Avahi fonctionne.
  Paramètres via variables d'environnement (port, chemins). Idéal pour reproduire
  sur une autre machine ou un hôte Docker en ligne.
- Paramètres exposés (env / config) : `PORT`, `LIBRARY_DIR`, `CATALOG_DB`,
  `INCOMING_DIR`, `DEVICES_DB` → aucun chemin en dur, pour la portabilité.

> Note Docker : le mDNS et l'accès au disque USB externe demandent le réseau hôte
> et un bind-mount ; documenté dans le README. Sur un hôte en ligne (sans les
> disques physiques), on pointe simplement `LIBRARY_DIR` vers un stockage monté.

---

## 9. Robustesse

- **Upload interrompu** : les fichiers non reçus réapparaîtront dans le prochain
  `/sync/plan` (le NUC ne les a pas au catalogue) → repris naturellement. Idempotent.
- **Intégrité** : chaque upload est **revérifié par empreinte** ; un fichier
  corrompu en transit est rejeté (l'app le renverra).
- **Concurrence** : verrou de tri (un commit à la fois). Le catalogue SQLite est
  partagé (lectures `has_hash` + écritures `add_media`) — connexion avec
  `timeout` pour tolérer les brefs verrous.
- **Sessions orphelines** : un `incoming/<session>/` sans commit est nettoyé
  (au démarrage du service, ou par âge).

---

## 10. Plan de test

- **Unitaires** : `devices` (création/validation/révocation de jeton),
  `pairing` (charge utile + génération QR), `sessions` (chemins, nettoyage).
- **Intégration** via le **`TestClient` de FastAPI** : une synchro simulée de
  bout en bout (plan → upload → commit) en dossiers temporaires, avec un
  catalogue temporaire ; vérifie le dédoublonnage (`/plan` ne redemande pas un
  fichier déjà au catalogue), l'intégrité (empreinte), le bilan de commit, et
  l'auth (401 sans jeton).
- `ingest` : le tri d'une session range bien dans la bibliothèque et nettoie
  `incoming/`.

---

## 11. Hors périmètre & renvois

- **Sous-projet 3** : app Android (scanner QR, scan dossiers, client d'upload,
  filtre par date de dernière synchro, bouton + auto-wifi).
- **Améliorations tracées en issues GitHub** : #2 (horizon de synchro initial),
  #3 (HTTPS + épinglage), #7 (sauvegarde Famille). Phase 2 : #4 (doublons),
  #5 (floues/rafales), #6 (re-datation). Optimisations : #8 (exiftool en lot),
  #9 (empreinte partielle).

---

## 12. Questions résolues / restantes

**Résolues :** architecture (FastAPI/Approche A), appairage (QR + secret par
appareil), anti-doublon (filtre date app + handshake empreintes NUC réutilisant
le catalogue), déclenchement (commit explicite b1), transport (HTTP v1),
découverte (mDNS `_mediaserve._tcp`), port (8787), dossier de réception
(`Famille/incoming/<session>/`, chemins préservés), **bilan de commit détaillé**
(+ enrichissement du `Report` de `mediasort`), **page web d'admin** (QR + liste/
révocation d'appareils + stats disque avec camembert SVG), **reproduction**
(README + Docker, chemins paramétrables).

**À confirmer à l'implémentation :** service systemd système vs utilisateur (selon
l'ordre de montage des disques).
