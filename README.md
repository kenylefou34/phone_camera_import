# phone_camera_import

Rapatrie les photos et vidéos d'un téléphone Android vers un ordinateur, puis
les range automatiquement par type et par date, sans jamais créer de doublon.

La bibliothèque obtenue ressemble à ça :

```
Famille/
├── Photos/2023/05 MAI/IMG_20230526_101530.jpg
├── Videos/2024/12 DÉCEMBRE/VID_20241224_193012.mp4
└── _A_TRIER/            ← les fichiers dont la date est introuvable
```

---

## Comment ça marche aujourd'hui

```
Téléphone  ──(1) WiFi──►  dossier unsorted/  ──(2) tri──►  bibliothèque rangée
```

1. **Rapatrier** — `run_backup.sh` copie les nouveaux fichiers du téléphone.
2. **Ranger** — `mediasort` les classe par date et écarte les doublons.
3. **Le serveur `phototheque`** — déjà en service sur le NUC, il fera les deux
   automatiquement dès que l'application Android existera (issue #12).

Aujourd'hui, ce sont les étapes 1 et 2 que tu utilises.

---

## 1. Rapatrier les médias du téléphone

### À faire une seule fois : préparer le téléphone

1. Installe **SimpleSSHD** depuis [F-Droid](https://f-droid.org/F-Droid.apk).
   L'application est aussi dans le dossier `resources/` de ce projet. Aucun
   accès root nécessaire.
2. Ouvre l'application, va dans les réglages.
3. Laisse le port sur **2222**.
4. Dans « Home Directory », mets `/storage/emulated/0/` — la racine de la
   mémoire du téléphone, là où se trouvent les photos.
5. Active « Start on Open » si tu veux que le serveur démarre à l'ouverture.

### À chaque sauvegarde

1. **Sur le téléphone** : ouvre SimpleSSHD et appuie sur « Start ».
   L'écran affiche une adresse du type `192.168.1.42` et un mot de passe à usage
   unique. Note les deux.

2. **Sur l'ordinateur**, place-toi dans le projet et lance le script :

   ```bash
   cd ~/phone_camera_import
   ./run_backup.sh
   ```

3. Le script pose trois questions :

   | Question | Quoi répondre |
   |---|---|
   | `Enter the phone last IP address number: 192.168.1.` | le dernier nombre de l'adresse affichée sur le téléphone, ici `42` |
   | `Enter the local destination path:` | le dossier de la bibliothèque, par exemple `/media/izquierdo/Famille` |
   | `Enter the option data to get (1-3):` | `1` appareil photo, `2` vidéos, `3` images (dont WhatsApp) |

4. Saisis le mot de passe affiché sur le téléphone quand il est demandé.

5. Le script copie les fichiers **nouveaux depuis la dernière fois**, puis lance
   le rangement. Tu dois voir défiler des noms de fichiers, puis un bilan :

   ```
   Bilan : 128 rangés, 12 doublons ignorés, 3 à trier, 0 exclus, 0 erreurs.
   Sauvegarde et rangement termines.
   ```

> Le script mémorise la date de la dernière sauvegarde **sur le téléphone**. La
> fois suivante, il ne reprend que ce qui est plus récent. Au tout premier
> lancement, il prend donc tout.

> Le nom d'utilisateur SSH est `ken` par défaut. S'il diffère sur ton téléphone :
> `SSH_USER=autrenom ./run_backup.sh`

### Optionnel : ne plus taper de mot de passe

1. Dans SimpleSSHD, réglages, « SSH Path » : choisis `/storage/emulated/0/.ssh/`.
2. Envoie ta clé publique sur le téléphone :

   ```bash
   scp -P 2222 ~/.ssh/id_rsa.pub ken@192.168.1.42:/storage/emulated/0/Download/
   ```

3. Connecte-toi une dernière fois avec le mot de passe :

   ```bash
   ssh -p 2222 ken@192.168.1.42
   ```

4. Dans cette session, installe la clé :

   ```bash
   mkdir -p /storage/emulated/0/.ssh
   cat /storage/emulated/0/Download/id_rsa.pub >> /storage/emulated/0/.ssh/authorized_keys
   chmod 700 /storage/emulated/0/.ssh
   chmod 600 /storage/emulated/0/.ssh/authorized_keys
   exit
   ```

5. Reconnecte-toi : aucun mot de passe ne doit être demandé.

> Le téléphone et l'ordinateur doivent être sur le **même réseau WiFi**.
> SimpleSSHD ne donne accès qu'aux dossiers qu'Android l'autorise à lire.

---

## 2. Ranger les médias

`run_backup.sh` le fait déjà en fin de course. Cette section sert quand tu veux
ranger un dossier à la main.

### Une seule fois : préparer l'ordinateur

```bash
sudo apt-get install -y libimage-exiftool-perl ffmpeg
```

`exiftool` et `ffmpeg` servent à lire la vraie date de prise de vue. Le trieur
lui-même n'a besoin de rien d'autre que Python.

### Une seule fois : amorcer le catalogue

Le catalogue est la mémoire de ce qui est déjà rangé : c'est lui qui évite les
doublons. On le remplit une fois à partir de la bibliothèque existante.

```bash
python3 -m mediasort --library /media/izquierdo/Famille --source /tmp/vide \
    --catalog ~/mediasort_catalog.db --seed --dry-run
```

Attendu : `Catalogue amorcé depuis ... : 44669 médias indexés.`
Compter un bon moment sur une grosse bibliothèque : chaque fichier est lu.

### Ranger un dossier

**D'abord une simulation**, qui ne déplace rien :

```bash
python3 -m mediasort --source /media/izquierdo/Famille/unsorted \
    --library /media/izquierdo/Famille --catalog ~/mediasort_catalog.db \
    --dry-run --verbose
```

Lis le bilan. Si les destinations te conviennent, **relance sans `--dry-run`** :

```bash
python3 -m mediasort --source /media/izquierdo/Famille/unsorted \
    --library /media/izquierdo/Famille --catalog ~/mediasort_catalog.db \
    --clean-noise
```

`--clean-noise` supprime au passage les fichiers parasites (vignettes, fichiers
techniques) laissés dans le dossier source.

### Comment la date est choisie

Dans cet ordre, en s'arrêtant au premier qui répond :

1. les **métadonnées** du fichier (EXIF pour les photos, conteneur pour les vidéos) ;
2. le **nom du fichier** (`IMG_20230526_101530.jpg`) ;
3. la **date système** du fichier ;
4. sinon le fichier part dans **`_A_TRIER/`** — rien n'est jamais jeté.

### Toutes les options

| Option | Rôle |
|---|---|
| `--source` | dossier à trier |
| `--library` | bibliothèque de destination |
| `--catalog` | fichier du catalogue anti-doublon |
| `--dry-run` | simulation : ne déplace rien |
| `--seed` | amorcer le catalogue avant de trier |
| `--seed-from` | dossier à indexer pour l'amorçage |
| `--clean-noise` | supprimer les fichiers parasites après le tri |
| `--backfill-signatures` | compléter un ancien catalogue (voir plus bas) |
| `--verbose` | journal détaillé |

---

## 3. Le serveur `phototheque`

Serveur qui reçoit les médias envoyés par le téléphone sans passer par un câble,
les range, et affiche une page d'administration. **Déjà installé sur le NUC.**

Installation ou mise à jour, en une commande :

```bash
cd ~/phone_camera_import && git pull && ./deploy/install.sh
```

Puis, dans un navigateur :

- `http://IZQUIERDO-NUC.local:8787/` — page d'administration
- `http://IZQUIERDO-NUC.local:8787/pair` — QR code d'appairage

**📖 [`docs/DEPLOIEMENT.md`](docs/DEPLOIEMENT.md)** détaille chaque étape, le
paramétrage, le dépannage, le retour en arrière et la variante Docker.

> L'application Android qui se connectera à ce serveur reste à écrire
> (issue #12). En attendant, la chaîne des sections 1 et 2 est la bonne.

---

## Pour aller plus loin

### Deux optimisations, et pourquoi elles existent

**Le pré-filtre par signature rapide.** Savoir si un fichier est un doublon
demande normalement de le lire en entier : près de 30 secondes pour une vidéo de
3 Go. Le trieur calcule donc d'abord une *signature* (taille + début + fin du
fichier, environ 130 Ko lus, **mille fois plus rapide**). Si cette signature est
inconnue du catalogue, le fichier est forcément nouveau et la lecture intégrale
est évitée.

Ce raccourci n'est sûr que si **toutes** les lignes du catalogue ont une
signature. Sur un catalogue créé avant cette fonctionnalité, le trieur le détecte
et désactive le raccourci — aucun risque de rater un doublon. Pour l'activer :

```bash
python3 -m mediasort --catalog ~/mediasort_catalog.db --backfill-signatures
```

Compter environ 15 minutes pour 45 000 médias. Une signature n'est **jamais** une
preuve d'égalité : quand elle correspond, l'empreinte complète est recalculée
pour trancher.

**L'empreinte calculée pendant la copie.** Quand un fichier est rangé, son
empreinte est calculée au fil de la copie : chaque bloc lu est à la fois haché et
écrit. Le fichier n'est donc traversé que deux fois au lieu de trois. Mesuré sur
une vidéo de 3,6 Go : **47,9 s → 34,9 s**.

Dans les deux cas la sûreté est intacte : la source n'est supprimée que si la
destination relue est identique octet pour octet. Si la vérification échoue, la
copie douteuse est retirée et la source reste en place.

### Lancer les tests

```bash
python3 -m pytest -q
```

Attendu : `115 passed`.

### Binaire C++ historique

Le dépôt contient encore `main.cpp`, la première version du trieur. Le trieur
Python le remplace et ne demande aucune compilation. Pour le construire malgré
tout :

```bash
sudo apt-get install -y build-essential cmake libopencv-dev libspdlog-dev \
    libfmt-dev libboost-all-dev
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j2
```

⚠️ Utiliser le **fmt du système** (`find_package(fmt)`), pas le sous-module
`modules/fmt` : les versions diffèrent et l'édition de liens échoue.

### Conception

Spécifications et plans détaillés dans `docs/superpowers/`.
