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

### Ce que tu dois voir

Neuf étapes numérotées, puis :

```
    /        200  ok
    /pair    200  ok
    /status  401  ok
    état      : active / enabled
    admin     : https://IZQUIERDO-NUC.local:8787/
```

`401` sur `/status` est **normal** : cette adresse exige une authentification.
Si le script s'arrête sur `ÉCHEC`, il dit quoi regarder.

### Le vocabulaire, en quatre phrases

- **systemd** est le chef d'orchestre des programmes qui tournent en fond sous
  Linux. Sans lui, il faudrait lancer le serveur à la main dans un terminal, et
  il s'arrêterait en le fermant.
- Un **service** (ou *unité*) est un fichier texte qui lui décrit quoi lancer,
  quand et comment. Le nôtre est `deploy/phototheque.service`.
- **`active`** veut dire « il tourne en ce moment ». **`enabled`** veut dire « il
  repartira tout seul au prochain démarrage du NUC ». Ce sont deux choses
  différentes, et on veut les deux.
- **Avahi** annonce la machine sur le réseau local sous `<nom d'hôte>.local`, ce
  qui évite de retenir une adresse IP.

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

### 3. Certificat du serveur

```bash
mkdir -p ~/.config/phototheque && chmod 700 ~/.config/phototheque
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -subj "/CN=$(hostname).local" \
    -addext "subjectAltName=DNS:$(hostname).local,DNS:localhost,IP:127.0.0.1" \
    -keyout ~/.config/phototheque/key.pem -out ~/.config/phototheque/cert.pem
```

Le service ne parle plus qu'en **HTTPS** : sans certificat, pas de démarrage.
N'ayant personne pour garantir ce certificat (pas d'autorité extérieure,
contrairement à un site public), il est **auto-signé** — d'où l'avertissement
du navigateur au premier accès, normal, détaillé plus bas.

Si le certificat existe déjà, le script le garde tel quel et affiche son
empreinte — c'est elle que l'application épingle pour reconnaître le NUC (voir
plus bas, section « Le certificat et le mot de passe »).

### 4. Mot de passe d'administration

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(12))"
```

Un mot de passe est tiré au hasard et son empreinte enregistrée dans
`~/.config/phototheque/admin` (jamais le mot de passe en clair). Il protège
`/`, `/pair`, `/devices` et la révocation d'un appareil.

**Il n'est affiché qu'une seule fois**, à la création :

```
    ┌─────────────────────────────────────────────┐
    │  Identifiants d'administration               │
    │  utilisateur : admin                         │
    │  mot de passe : xxxxxxxxxxxxxxxxxxxxxxxxxx   │
    └─────────────────────────────────────────────┘
```

**Note-le tout de suite.** Si le fichier `admin` existe déjà, cette étape ne
fait rien et n'affiche rien : le mot de passe en place est conservé. Pour en
changer, voir la section « Le certificat et le mot de passe » plus bas.

### 5. Retrait de l'ancien service

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

### 6. Reprise des appairages

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

> **Pourquoi le contenu et pas l'existence.** Le 17/09/2026,
> `phototheque/app.py` instanciait `DeviceStore` au chargement du module :
> **importer l'application suffisait à créer la base, vide**. Lancer les tests
> sur le NUC créait donc `~/phototheque_devices.db`, et le test d'existence en
> a conclu à tort que la reprise avait déjà eu lieu. La base n'est désormais
> ouverte qu'à la première utilisation réelle, mais le critère reste le
> contenu : une base vide traînante ne doit jamais bloquer la reprise.

Le catalogue des médias, lui, ne change pas de nom : il s'appelle
`~/mediasort_catalog.db` d'après le trieur, qui n'a pas été renommé.

### 7. Le port est-il libre ?

```bash
ss -lptn 'sport = :8787'
```

Filet de sécurité avant de démarrer : même sans ancienne unité, un `uvicorn`
lancé à la main peut tenir le port. Le script s'arrête avec un message clair
plutôt que de laisser systemd boucler.

### 8. Installation de l'unité systemd et de l'annonce réseau

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
  redémarrage. C'est lui qui permet d'écrire `https://IZQUIERDO-NUC.local:8787`
  au lieu de retenir l'adresse IP, et qui permettra à l'app Android de trouver
  le NUC seule.

> **Le nom d'hôte compte.** La machine s'annonce sous `<nom d'hôte>.local`,
> ici `IZQUIERDO-NUC.local`. `nuc.local` ne résout pas. L'URL publiée dans le
> QR d'appairage est donc déduite du nom d'hôte réel (`PUBLIC_URL` dans
> `phototheque/config.py`) et non écrite en dur — sinon l'app scannerait une
> adresse injoignable. Vérifier ce qui est réellement annoncé, depuis une
> autre machine du réseau :
> ```bash
> avahi-browse -tpr _phototheque._tcp
> ```

**Nom convivial (facultatif).** Par défaut l'annonce réseau porte
`phototheque sur <nom d'hôte>` (ex. `phototheque sur IZQUIERDO-NUC`), un nom
technique. Pour afficher autre chose (« Photothèque du salon ») :

```bash
echo "Photothèque du salon" > ~/.config/phototheque/nom
./deploy/install.sh
```

Un fichier absent, vide ou ne contenant que des espaces retombe sur le nom par
défaut — jamais sur une annonce sans nom.

`enable` et `active` sont deux choses distinctes : `active` veut dire « il tourne
en ce moment », `enabled` veut dire « il repartira au prochain démarrage ».

### 9. Vérification

Il n'y a **pas de `curl` sur le NUC** : on interroge avec Python. Le certificat
étant auto-signé, personne ne le garantit pour Python non plus : on désactive
donc la vérification pour cet appel local, avec
`ssl._create_unverified_context()`.

```bash
~/.venv-server/bin/python -c "
import ssl, urllib.request
contexte = ssl._create_unverified_context()
for p in ('/', '/pair'):
    print(p, urllib.request.urlopen('https://127.0.0.1:8787' + p, timeout=5,
                                     context=contexte).status)
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

## Le certificat et le mot de passe

`install.sh` fabrique les deux à la première installation, dans
`~/.config/phototheque/` :

| Fichier | Rôle | Si tu le supprimes |
|---|---|---|
| `cert.pem`, `key.pem` | certificat du serveur | un nouveau est fabriqué — **tous les téléphones appairés sont rejetés** et doivent être réappairés |
| `admin` | empreinte du mot de passe | un nouveau mot de passe est tiré et affiché |
| `nom` | nom affiché sur le réseau (facultatif) | retour à « phototheque sur <machine> » |

**Ne supprime jamais le certificat sans raison.** L'application épingle son
empreinte : la changer revient à changer d'identité aux yeux des téléphones.

**Mot de passe perdu ou à changer :**

```bash
rm ~/.config/phototheque/admin
./deploy/install.sh
```

Le script relance la fabrication (étape 4/9) et affiche un nouveau mot de
passe — **une seule fois**, comme à la première installation. Note-le
immédiatement.

### Migrer vers une autre machine

Le téléphone retrouve le serveur par le réseau, pas par son adresse : il cherche
le service `_phototheque._tcp` et reconnaît le bon au certificat. Deux façons de
déménager :

**Garder les appairages** — copier la configuration et les données :

```bash
scp -r ~/.config/phototheque nouvelle-machine:~/.config/
scp ~/mediasort_catalog.db ~/phototheque_devices.db nouvelle-machine:~/
```

Puis `./deploy/install.sh` sur la nouvelle machine. Les téléphones continuent de
fonctionner sans rien faire. Réserve : le certificat copié porte les noms de
l'ancienne machine, donc le navigateur redeviendra avertissant.

**Repartir propre** — ne rien copier, lancer `./deploy/install.sh`, puis
réappairer chaque téléphone avec un nouveau QR.

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
| `Address already in use` | Ancien service encore actif | `systemctl list-unit-files \| grep -E 'mediaserve\|phototheque'` puis retirer l'ancien (étape 5) |
| L'adresse `.local` est inaccessible, l'IP fonctionne | Annonce mDNS absente, ou mauvais nom d'hôte | `sudo systemctl restart avahi-daemon` ; vérifier le nom réel avec `hostname` et ce qui est annoncé avec `avahi-browse -tpr _phototheque._tcp` depuis une autre machine |
| `http://IZQUIERDO-NUC.local:8787/` ne répond plus, message peu explicite du navigateur | Le service ne parle plus qu'en HTTPS : un même port ne sert pas les deux protocoles | Taper `https://IZQUIERDO-NUC.local:8787/` |
| Le navigateur affiche un avertissement de sécurité en `https://` | Certificat auto-signé — normal, personne d'extérieur ne le garantit | Cliquer « Paramètres avancés » puis « Continuer » ; une fois par appareil |
| Mot de passe d'administration perdu | — | `rm ~/.config/phototheque/admin && ./deploy/install.sh` : un nouveau est tiré et affiché |
| Téléphones soudain non reconnus | Base d'appairage perdue | Vérifier `~/phototheque_devices.db` ; l'ancienne était `~/mediaserve_devices.db` (étape 6) |
| Le QR d'appairage reste blanc | Page servie par une version antérieure au correctif | Relancer `git pull && ./deploy/install.sh` : le code n'est pas rechargé tout seul |
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
| `CONFIG_DIR` | `~/.config/phototheque` | Dossier du certificat, du mot de passe et du nom convivial |
| `CERT_FILE` | `<CONFIG_DIR>/cert.pem` | Certificat TLS du serveur |
| `KEY_FILE` | `<CONFIG_DIR>/key.pem` | Clé privée du certificat |
| `ADMIN_FILE` | `<CONFIG_DIR>/admin` | Empreinte du mot de passe d'administration |
| `PUBLIC_URL` | `https://<nom d'hôte>.local:<PORT>` | Adresse publiée dans le QR d'appairage |

---

## Variante Docker

Cette section est écrite pour être suivie sans rien connaître à Docker. Tout ce
qui suit a été exécuté et vérifié, pas seulement rédigé.

### Faut-il l'utiliser ?

**Sur le NUC, non.** Le déploiement recommandé reste `./deploy/install.sh`
(section précédente) : c'est lui qui est en service et qui gère le montage du
disque, le démarrage au boot et l'annonce réseau.

Docker sert à **faire tourner le service sur une autre machine sans y installer
quoi que ce soit** : essayer sur un portable, migrer vers un autre ordinateur,
ou repartir de zéro si le NUC rend l'âme. Tout ce dont l'application a besoin
(Python, exiftool, ffmpeg) est enfermé dans une boîte, et la machine hôte reste
propre.

### Le vocabulaire, en trois phrases

- Une **image**, c'est un modèle figé : l'application et tous ses outils,
  empaquetés. On la fabrique une fois.
- Un **conteneur**, c'est une image qu'on fait tourner. On peut l'arrêter, le
  supprimer et le recréer sans rien perdre, à condition que les données soient
  dans des volumes (voir plus bas).
- Un **volume**, c'est un dossier qui survit au conteneur. C'est là que vivent
  tes photos et le catalogue.

### 1. Installer Docker

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker "$USER"
```

La dernière ligne t'évite de taper `sudo` devant chaque commande Docker.
**Elle ne prend effet qu'après une déconnexion/reconnexion** — ferme ta session
et rouvre-la, sinon tu auras « permission denied ».

Vérifie que tout répond :

```bash
docker run --rm hello-world
docker compose version
```

> **Attention au piège « compose ».** Il existe deux versions.
> La moderne s'écrit **`docker compose`** (avec une **espace**), fournie par le
> paquet `docker-compose-plugin`. L'ancienne s'écrit `docker-compose` (avec un
> **tiret**) : elle n'est plus maintenue et **plante avec les versions récentes
> de Docker**, sur une erreur incompréhensible du type
> `HTTPConnection.request() got an unexpected keyword argument 'chunked'`.
> Si tu vois cette erreur, c'est que tu utilises l'ancienne : installe
> `docker-compose-plugin` et remets l'espace.

### 2. Indiquer où sont les photos

Ouvre `deploy/docker-compose.yml` et adapte **une seule ligne**, celle du
dossier de la bibliothèque sur ta machine :

```yaml
    volumes:
      # À ADAPTER : dossier de la bibliothèque sur la machine hôte.
      - /media/izquierdo/Famille:/data/library
```

À gauche des deux-points, le chemin **sur ta machine**. À droite, le chemin
**vu par l'application** : celui-là ne change jamais. Sur un portable, ce serait
par exemple `/home/ken/Photos:/data/library`.

Le dossier doit exister avant de démarrer, sinon Docker en crée un vide et tu
croiras la bibliothèque perdue.

### 3. Démarrer

Depuis la racine du dépôt :

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

- `--build` fabrique l'image. **La première fois prend plusieurs minutes** (il
  télécharge Python, exiftool et ffmpeg) ; les fois suivantes sont rapides.
- `-d` (*detached*) rend la main : le service tourne en arrière-plan.

### 4. Vérifier

```bash
docker compose -f deploy/docker-compose.yml ps        # doit afficher « running »
```

Puis ouvre `http://localhost:8787/` dans un navigateur. Tu dois voir la page
d'administration. `http://localhost:8787/pair` affiche le QR d'appairage.

En cas de doute, lis ce que dit l'application :

```bash
docker compose -f deploy/docker-compose.yml logs -f   # Ctrl-C pour sortir
```

### 5. Les commandes du quotidien

| Ce que tu veux | La commande (depuis la racine du dépôt) |
|---|---|
| Voir les journaux | `docker compose -f deploy/docker-compose.yml logs -f` |
| Arrêter | `docker compose -f deploy/docker-compose.yml stop` |
| Redémarrer | `docker compose -f deploy/docker-compose.yml restart` |
| Mettre à jour après un `git pull` | `docker compose -f deploy/docker-compose.yml up -d --build` |
| Tout arrêter et supprimer le conteneur | `docker compose -f deploy/docker-compose.yml down` |

`down` supprime le conteneur mais **garde les données**. Redémarrer ensuite
retrouve le catalogue et les appareils appairés.

### Où sont les données, et comment les sauvegarder

Deux endroits, à ne pas confondre :

| Donnée | Où elle vit | Perdue si… |
|---|---|---|
| **Tes photos et vidéos** | sur ta machine, dans le dossier que tu as indiqué à l'étape 2 | jamais par Docker — c'est ton dossier |
| **Catalogue + appareils appairés** | dans un volume Docker nommé `phototheque-data` | seulement si tu le supprimes explicitement |

Pour sauvegarder le catalogue, commence par **relever le nom exact du volume** :
Docker le préfixe par le nom du projet, qui dépend du dossier depuis lequel tu
lances la commande. Ne le devine pas, demande-le :

```bash
docker volume ls | grep phototheque-data
```

Reporte le nom affiché à la place de `<VOLUME>` ci-dessous :

```bash
docker compose -f deploy/docker-compose.yml stop
docker run --rm -v <VOLUME>:/data -v "$PWD":/sauvegarde \
    alpine tar czf /sauvegarde/catalogue-phototheque.tgz -C /data .
docker compose -f deploy/docker-compose.yml start
```

Tu obtiens un fichier `catalogue-phototheque.tgz` dans le dossier courant.

### Les limites, dites franchement

- **La découverte réseau (mDNS) ne fonctionne pas** dans cette variante.
  L'adresse `IZQUIERDO-NUC.local` est annoncée par Avahi, un service de la
  machine hôte, et l'application ne fait aucune annonce elle-même. En Docker, il
  faut donc utiliser `http://localhost:8787` en local, ou l'adresse IP de la
  machine depuis un téléphone. Pour retrouver le nom `.local`, installe le
  fichier d'annonce sur l'hôte comme à l'étape 8 de la section systemd.
  Pense alors à renseigner `PUBLIC_URL` (tableau du paramétrage ci-dessus) pour
  que le QR code affiche une adresse joignable depuis le téléphone.
- **Le conteneur sert en HTTP, pas en HTTPS.** Le certificat est fabriqué par
  `install.sh`, que la variante Docker n'utilise pas. Conséquence à connaître :
  l'adresse publiée dans le QR d'appairage vaut `https://…` par défaut, alors
  que le conteneur ne répond qu'en `http://`. L'application ne pourrait pas se
  connecter. Si tu utilises cette variante avec un téléphone, force l'adresse :
  `PUBLIC_URL=http://<adresse-de-la-machine>:8787` dans `docker-compose.yml`.
  Pour un simple essai depuis un navigateur, il n'y a rien à faire.
- **Les fichiers créés par le conteneur appartiennent à `root`** sur ta machine
  (le conteneur tourne en root). C'est sans gravité, mais ça surprend quand on
  essaie de les effacer sans `sudo`.
- Le port 8787 doit être libre. S'il est déjà pris (par exemple par le service
  systemd sur le NUC), Docker refusera de démarrer.

### Tout supprimer

```bash
docker compose -f deploy/docker-compose.yml down -v   # -v supprime AUSSI les données
docker image prune -a                                  # libère les images inutilisées
```

⚠️ `-v` efface le volume, donc le catalogue et les appareils appairés. **Tes
photos ne sont pas touchées** : elles sont dans ton dossier, pas dans le volume.
