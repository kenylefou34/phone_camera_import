Here’s how to use **SimpleSSHD** on Android to synchronize your files with rsync from Linux:

***

### 1. Install SimpleSSHD on Your Phone

- Download the SimpleSSHD from [F-Droid](https://f-droid.org/F-Droid.apk) app (you may have to update the app after launching it), also available in the resource folder of this project.
- Install it as usual (no root required).


### 2. Configure SimpleSSHD

- Open the app and go to the settings.
- The default SSH port is **2222**; leave it or change it if you want.
- Optionally: in "Home Directory," set the path you want to share (e.g., `/storage/emulated/0/Download/` for the "Download" folder).
- You can enable "Start on boot" or "Start on Open" as you prefer.
- You can disable entering password for each ssh request, see section 8. 

### 3. Start the SSH Server

- On your phone, tap "Start."
- Your local network IP (WiFi) appears at the top; note it to connect.


### 4. Connect via SSH

- From your Linux PC, connect using:

```bash
ssh -p 2222 username@PHONE_IP_ADDRESS
```

    - Replace `username` with the one shown on your phone, if provided, else choose one.
    - The initial password is shown on your phone screen; you can later set up your SSH public key for secure and convenient login.


### 5. Sync With rsync

- To copy files with rsync:

```bash
rsync -avz -e "ssh -p 2222" username@PHONE_IP_ADDRESS:/storage/emulated/0/Download/ /path/to/destination/on-PC/
```

    - Adjust the source and destination paths as needed.


### 6. Secure Your Access (Optional but Recommended)

- Add your SSH public key to the `authorized_keys` file on your phone so you don’t have to enter a password every time.


### 7. Bash script 

- A script named `run_backup.sh` handle synchronization steps (4 & 5).

### 8. Example to transfer your public key:

- In `SimmpleSSHD` app `Setting`, `SSH Path`, select the path you choose for example `/storage/emulated/0/.ssh/`.

```bash
scp -P 2222 /storage/emulated/0/.ssh/id_rsa.pub "$SSH_USER@$PHONE_IP:/storage/emulated/0/Download/id_rsa.pub"
```

- Here, `-P 2222` specifies the SSH port used by SimpleSSHD.
- The file is copied to the phone’s `Download` folder, for example.
- You can then point SimpleSSHD to this path as the `authorized_keys` file or copy this file to the correct location on the phone.

### 8.1. Then, to install your key in the remote `authorized_keys` file (if necessary):

1. Connect via SSH with password:
```bash
ssh -p 2222 "$SSH_USER@$PHONE_IP"
```

2. In the remote session, create the `.ssh` directory if needed and append the public key:
```bash
cat /storage/emulated/0/Download/id_rsa.pub >> ~/.ssh/authorized_keys
chmod 700 /storage/emulated/0/.ssh
chmod 600 /storage/emulated/0/.ssh/authorized_keys
```

3. Exit the session and try reconnecting via SSH — this time without a password prompt.

This method works to automate SSH connections (and thus rsync, scp, etc.) with SimpleSSHD, so you don’t have to enter your password every time.

***

**Notes:**

- SimpleSSHD only grants access to folders for which it has permission (usually internal storage, sometimes the SD card depending on Android version).
- Transfers occur over WiFi, so your PC and phone must be on the same local network.

This setup allows you to easily sync files between your Android phone and Linux PC, taking full advantage of rsync’s speed and reliability over SSH.


---

## Trieur de médias (Python)

Range un dossier source de photos/vidéos dans une bibliothèque classée par
type et par date (`Photos|Videos/ANNÉE/"MM MOIS"`), en lisant la vraie date de
prise de vue et sans jamais créer de doublon.

### Mise en place de l'environnement

```bash
# Outils système (dates de prise de vue) :
sudo apt-get install -y libimage-exiftool-perl ffmpeg

# Pour lancer les tests (optionnel) : pytest
python3 -m pip install --user pytest
# (mediasort lui-même ne dépend que de la bibliothèque standard Python.)
```

### Utilisation

```bash
# 1) Amorcer le catalogue depuis la bibliothèque existante (une fois) :
python3 -m mediasort --library /media/izquierdo/Famille --source /tmp/vide --seed --dry-run

# 2) Simulation du tri d'un dossier (rien n'est déplacé) :
python3 -m mediasort --source /media/izquierdo/Famille/unsorted \
                     --library /media/izquierdo/Famille --dry-run --verbose

# 3) Tri réel + nettoyage du bruit :
python3 -m mediasort --source /media/izquierdo/Famille/unsorted \
                     --library /media/izquierdo/Famille --clean-noise
```

Options : `--source`, `--library`, `--catalog FICHIER.db`, `--dry-run`,
`--seed`, `--clean-noise`, `--verbose`, `--backfill-signatures`.

### Pré-filtre par signature rapide (grosses vidéos)

Pour savoir si un fichier est un doublon, le trieur calcule normalement son
empreinte complète (SHA-256), ce qui suppose de **lire tout le fichier** : près
de 30 secondes pour une vidéo de 3 Go.

Le trieur calcule donc d'abord une *signature rapide* (taille + début + fin du
fichier, ~130 Ko lus, environ **1000 fois plus rapide**). Si cette signature
n'existe pas dans le catalogue, le fichier est forcément nouveau : la lecture
intégrale est évitée.

Ce raccourci n'est sûr que si **toutes** les lignes du catalogue ont une
signature. Sur un catalogue créé avant cette fonctionnalité, elles sont vides :
le trieur détecte ce cas et désactive le raccourci (aucun risque de rater un
doublon). Pour le réactiver, on complète les signatures une bonne fois :

```bash
# Ne lit que le début et la fin de chaque média déjà catalogué.
# Compter environ 1 heure pour 45 000 médias sur un disque USB.
python3 -m mediasort --catalog ~/mediasort_catalog.db --backfill-signatures
```

Une signature n'est **jamais** une preuve d'égalité : quand elle correspond à
une entrée connue, l'empreinte complète est calculée pour trancher.

### Empreinte calculée pendant la copie

Quand un fichier est réellement rangé, son empreinte est calculée **au fil de la
copie** : chaque bloc lu est à la fois haché et écrit. Le fichier n'est donc
traversé que deux fois (lecture de la source, relecture de la destination pour
vérifier) au lieu de trois. Mesuré sur le NUC avec une vidéo de 3,6 Gio :
**47,9 s → 34,9 s (-27 %)**.

La garantie de sûreté est inchangée : la source n'est supprimée que si la
destination relue est identique octet pour octet, et les métadonnées (dont la
date de modification, qui sert de dernier recours à la datation) sont conservées.

### Tests

```bash
python3 -m pytest -v
```

---

## Service d'ingestion (mediaserve)

Serveur FastAPI qui reçoit les médias poussés par le téléphone (sans doublon),
les range via le trieur, et s'annonce en mDNS. Voir le spec
`docs/superpowers/specs/2026-09-14-service-ingestion-design.md`.

### Mise en place (machine Linux)
```bash
sudo apt-get install -y libimage-exiftool-perl ffmpeg python3-venv
python3 -m venv ~/.venv-server
~/.venv-server/bin/pip install -r requirements-server.txt
# Lancement manuel :
~/.venv-server/bin/uvicorn mediaserve.app:app --host 0.0.0.0 --port 8787
```
Puis, pour le démarrage automatique et la découverte réseau :
```bash
sudo cp deploy/mediaserve.service /etc/systemd/system/ && sudo systemctl enable --now mediaserve
sudo cp deploy/avahi-mediaserve.service /etc/avahi/services/
```
Ouvre `http://nuc.local:8787/` (admin) et `http://nuc.local:8787/pair` (QR).

Chemins paramétrables par variables d'environnement : `PORT`, `LIBRARY_DIR`,
`CATALOG_DB`, `INCOMING_DIR`, `DEVICES_DB`.

### Reproduction en Docker
```bash
docker compose -f deploy/docker-compose.yml up -d --build
```
`network_mode: host` est nécessaire pour le mDNS ; le dossier médias est monté en
volume (`LIBRARY_DIR=/data/library`). Sur un hôte en ligne sans les disques
physiques, pointe simplement `LIBRARY_DIR` vers un stockage monté.
