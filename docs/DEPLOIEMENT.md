# Déploiement de `phototheque` sur le NUC

Comment installer, mettre à jour et dépanner le service d'ingestion. Tout est
en français et détaillé : l'objectif est que tu puisses rejouer l'opération
seul, en comprenant ce que fait chaque commande.

> Le module s'appelait `mediaserve` jusqu'au 17/09/2026. Si tu tombes sur ce
> nom dans un ancien document, c'est le même composant.

---

## En une commande

Depuis la racine du dépôt, **sur le NUC, dans un vrai terminal** :

```bash
cd ~/phone_camera_import
git pull
./deploy/install.sh
```

C'est tout. Le script est **idempotent** : le relancer ne casse rien, il remet
simplement l'installation dans l'état voulu. C'est la commande à rejouer après
chaque modification du code.

Il demande ton mot de passe `sudo` : deux étapes touchent au système (l'unité
systemd et le fichier Avahi). D'où le « vrai terminal » — un canal sans TTY ne
peut pas saisir de mot de passe.

---

## Ce que fait le script, étape par étape

Si tu veux le faire à la main, ou comprendre ce qui se passe, voici l'équivalent
de chaque étape.

### 1. Vérifications préalables

Le script contrôle qu'il est bien lancé depuis le dépôt et que les fichiers
attendus existent. Il prévient aussi si le disque de la bibliothèque n'est pas
monté :

```bash
mountpoint -q /media/izquierdo/Famille && echo monté || echo "NON monté"
```

Ce n'est pas bloquant : l'unité systemd contient `RequiresMountsFor`, donc le
service attendra le montage au lieu de démarrer dans le vide.

### 2. Environnement Python

```bash
python3 -m venv ~/.venv-server
~/.venv-server/bin/pip install -r requirements-server.txt
```

**Pourquoi un venv ?** Ubuntu applique la PEP 668 : le Python du système refuse
`pip install --user` pour éviter d'abîmer les paquets gérés par `apt`. On
installe donc les dépendances dans un environnement isolé, `~/.venv-server`.
C'est aussi pour ça que l'unité systemd appelle `~/.venv-server/bin/uvicorn` et
non `uvicorn` tout court.

Le trieur `mediasort`, lui, n'a besoin d'aucune dépendance : il n'utilise que la
bibliothèque standard. Seuls `exiftool` et `ffmpeg` lui sont utiles, côté système :

```bash
sudo apt-get install -y libimage-exiftool-perl ffmpeg
```

### 3. Retrait de l'ancien service

```bash
sudo systemctl disable --now mediaserve.service
sudo rm -f /etc/systemd/system/mediaserve.service
sudo rm -f /etc/avahi/services/avahi-mediaserve.service
sudo systemctl daemon-reload
```

**C'est le piège du renommage.** Installer le nouveau service sans retirer
l'ancien laisse deux unités actives qui se disputent le port 8787 : la seconde
échoue au démarrage, redémarre en boucle, et les journaux deviennent illisibles.

Cette étape vient **avant** la reprise des données, et ce n'est pas un détail :
déplacer une base SQLite pendant que le processus qui l'écrit tourne encore
donne un état incohérent.

> **Comment cette étape a échoué le 17/09/2026.** Le script testait la présence
> de l'ancien service avec `systemctl list-unit-files | grep -q "^mediaserve"`.
> Sous `set -o pipefail`, `grep -q` s'arrête au premier résultat et ferme le
> tuyau ; `systemctl`, qui a encore beaucoup à écrire, reçoit SIGPIPE et sort en
> 141 ; le pipeline renvoie donc 141 **alors que la correspondance existait**.
> La condition était inversée, le nettoyage sauté. La détection se fait
> maintenant sur l'existence du fichier d'unité — déterministe, sans pipeline.

### 4. Reprise des appairages

```bash
mv ~/mediaserve_devices.db ~/phototheque_devices.db
```

La base des **appareils appairés** portait l'ancien nom. Sans cette reprise, le
service redémarrerait avec zéro appareil connu et les téléphones déjà appairés
seraient rejetés — il faudrait tout réappairer au QR code.

Le script décide d'après le **contenu** des bases, pas d'après l'existence du
fichier : il reprend si l'ancienne contient des appareils et la nouvelle aucun,
et n'écrase jamais une base déjà peuplée. Une base vide rencontrée au passage
est mise de côté sous `*.vide-<horodatage>` plutôt que supprimée.

> **Pourquoi le contenu et pas l'existence.** `phototheque/app.py` instancie
> `DeviceStore` au chargement du module : **importer l'application suffit à
> créer la base, vide**. Un simple `lancer les tests` sur le NUC crée donc
> `~/phototheque_devices.db`, et un test d'existence en conclut à tort que la
> reprise a déjà eu lieu. C'est exactement ce qui s'est produit le 17/09/2026.

Le catalogue des médias, lui, ne change pas de nom : il s'appelle
`~/mediasort_catalog.db` d'après le trieur, qui n'a pas été renommé.

### 5. Le port est-il libre ?

```bash
ss -lptn 'sport = :8787'
```

Filet de sécurité avant de démarrer : même sans ancienne unité, un `uvicorn`
lancé à la main peut tenir le port. Le script s'arrête avec un message clair
plutôt que de laisser systemd boucler.

### 6. Installation de l'unité systemd et de l'annonce réseau

```bash
sudo cp deploy/phototheque.service /etc/systemd/system/
sudo cp deploy/avahi-phototheque.service /etc/avahi/services/
sudo systemctl daemon-reload
sudo systemctl enable --now phototheque.service
sudo systemctl restart avahi-daemon
```

- **`daemon-reload`** : systemd relit ses fichiers de configuration. Sans ça, il
  continue d'utiliser l'ancienne version en mémoire.
- **`enable`** : le service démarrera automatiquement à chaque boot du NUC.
- **`--now`** : et démarre aussi tout de suite.
- **`restart avahi-daemon`** : Avahi ne relit ses fichiers de service qu'au
  redémarrage. C'est lui qui permet d'écrire `http://nuc.local:8787` au lieu de
  retenir l'adresse IP, et qui permettra à l'app Android de trouver le NUC seule.

`enable` et `active` sont deux choses distinctes : `active` veut dire « il tourne
en ce moment », `enabled` veut dire « il repartira au prochain démarrage ».

### 7. Vérification

Il n'y a **pas de `curl` sur le NUC** : on interroge avec Python.

```bash
~/.venv-server/bin/python -c "
import urllib.request
for p in ('/', '/pair'):
    print(p, urllib.request.urlopen('http://127.0.0.1:8787' + p, timeout=5).status)
"
```

Résultat attendu : `200` sur `/` et `/pair`. La route `/status` répond
volontairement **401** sans authentification — c'est le comportement correct, pas
une panne.

Le script contrôle aussi que le service est bien `active` après démarrage : un
service en boucle de redémarrage ne doit pas passer pour une installation
réussie.

### Les décisions du script sont testées

Les deux décisions qui se sont trompées le 17/09/2026 (détecter l'ancien
service, décider de reprendre les appairages) sont isolées dans
`deploy/lib.sh`, sans effet de bord, et couvertes par `tests/test_deploy.py`.
Un test interdit par ailleurs de décider à partir d'un pipeline, la cause de la
première panne.

---

## Après une modification du code

```bash
cd ~/phone_camera_import
git pull
./deploy/install.sh
```

**Le code n'est jamais rechargé tout seul.** `uvicorn` tourne sans `--reload` en
production : tant qu'on ne redémarre pas le service, il continue d'exécuter la
version chargée en mémoire au démarrage. Le script s'en charge (`systemctl
restart`), mais si tu veux juste redémarrer sans rien réinstaller :

```bash
sudo systemctl restart phototheque
```

---

## Consulter et dépanner

```bash
systemctl status phototheque         # état détaillé (lecture : pas besoin de sudo)
journalctl -u phototheque -f         # journal en direct
journalctl -u phototheque -n 50      # les 50 dernières lignes
journalctl -u phototheque -b         # depuis le dernier démarrage du NUC
```

| Symptôme | Cause probable | Quoi faire |
|---|---|---|
| Le service ne démarre pas au boot | Disque `Famille` non monté | `mountpoint -q /media/izquierdo/Famille` ; l'unité l'attend via `RequiresMountsFor`, il suffit de monter le disque |
| `Address already in use` | Ancien service encore actif | `systemctl list-unit-files \| grep -E 'mediaserve\|phototheque'` puis retirer l'ancien (étape 4) |
| `http://nuc.local:8787` inaccessible, l'IP fonctionne | Annonce mDNS absente | `sudo systemctl restart avahi-daemon` ; vérifier `/etc/avahi/services/avahi-phototheque.service` |
| Téléphones soudain non reconnus | Base d'appairage perdue | Vérifier `~/phototheque_devices.db` ; l'ancienne était `~/mediaserve_devices.db` (étape 3) |
| `database is locked` | Écriture concurrente sur le catalogue | Vérifier qu'un `--backfill-signatures` ne tourne pas : `pgrep -af "python3 -m mediasort"` |

### Revenir en arrière

Les unités systemd sont de simples fichiers texte, la marche arrière est directe :

```bash
sudo systemctl disable --now phototheque
sudo rm /etc/systemd/system/phototheque.service
sudo rm /etc/avahi/services/avahi-phototheque.service
sudo systemctl daemon-reload
```

Pour revenir à une version antérieure du code : `git log --oneline` pour trouver
le commit, `git checkout <commit>`, puis `./deploy/install.sh`.

Le catalogue est sauvegardé avant les opérations lourdes. Pour le restaurer :

```bash
sudo systemctl stop phototheque
cp ~/mediasort_catalog.db.avant-signatures ~/mediasort_catalog.db
sudo systemctl start phototheque
```

---

## Paramétrage

Tout est surchargeable par variables d'environnement (voir
`phototheque/config.py`), à déclarer dans l'unité systemd avec `Environment=` :

| Variable | Défaut | Rôle |
|---|---|---|
| `PORT` | `8787` | Port d'écoute |
| `LIBRARY_DIR` | `/media/izquierdo/Famille` | Bibliothèque de destination |
| `CATALOG_DB` | `~/mediasort_catalog.db` | Catalogue anti-doublon |
| `INCOMING_DIR` | `<LIBRARY_DIR>/incoming` | Dépôt temporaire des envois |
| `DEVICES_DB` | `~/phototheque_devices.db` | Appareils appairés |

---

## Variante Docker

Pour reproduire ailleurs sans toucher au système hôte :

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

`network_mode: host` est nécessaire au mDNS. Sur une machine sans les disques
physiques, il suffit de pointer `LIBRARY_DIR` vers un stockage monté.
