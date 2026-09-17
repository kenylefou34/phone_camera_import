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

### 3. Reprise des données de l'ancien nom

```bash
mv ~/mediaserve_devices.db ~/phototheque_devices.db
```

La base des **appareils appairés** portait l'ancien nom. Sans cette reprise, le
service redémarrerait avec zéro appareil connu et les téléphones déjà appairés
seraient rejetés — il faudrait tout réappairer au QR code.

Le script ne le fait que si l'ancien fichier existe et que le nouveau n'existe
pas encore, donc le relancer est sans danger.

Le catalogue des médias, lui, ne change pas de nom : il s'appelle
`~/mediasort_catalog.db` d'après le trieur, qui n'a pas été renommé.

### 4. Retrait de l'ancien service

```bash
sudo systemctl disable --now mediaserve.service
sudo rm -f /etc/systemd/system/mediaserve.service
sudo rm -f /etc/avahi/services/avahi-mediaserve.service
```

**C'est le piège du renommage.** Installer le nouveau service sans retirer
l'ancien laisse deux unités actives qui se disputent le port 8787 : la seconde
échoue au démarrage, redémarre en boucle, et les journaux deviennent illisibles.

### 5. Installation de l'unité systemd et de l'annonce réseau

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

### 6. Vérification

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
