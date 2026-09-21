# L'application Android, de zéro

Mode d'emploi complet : monter la machine de compilation, construire
l'application, la déposer sur le NUC, l'installer sur un téléphone, l'appairer.

Écrit pour être utilisable **des mois plus tard, sans rien avoir retenu**. Rien
n'est supposé installé, rien n'est supposé su. Le serveur, lui, a sa propre
documentation : [`DEPLOIEMENT.md`](DEPLOIEMENT.md).

---

## 1. En quatre phrases

L'application vit sur le téléphone. Elle regarde les dossiers de photos, envoie
au NUC ce qu'il n'a pas encore, et le NUC les range dans la bibliothèque
familiale par année et par mois.

Elle est écrite en **Kotlin natif**. Son code est dans `android/`, dans ce même
dépôt que le serveur — pour qu'une évolution du serveur et l'adaptation de
l'application tiennent dans le même commit.

Elle n'est **pas** sur le Play Store. On construit un fichier `.apk` et on
l'installe à la main.

Le NUC ne peut pas la construire : il n'a ni JDK ni SDK Android, 2 cœurs et
3 Go de mémoire. **Toute la compilation se fait sur le poste de développement.**

## 2. La chaîne complète

```
   Poste de développement                NUC                    Téléphone
  ┌────────────────────────┐      ┌──────────────────┐      ┌──────────────┐
  │ android/  (le code)    │      │                  │      │              │
  │   ↓ ./gradlew          │      │                  │      │              │
  │ app-debug.apk  25 Mo   │─────▶│ ~/.local/share/  │─────▶│  installée   │
  │   ↑ envoyer-apk.sh     │ scp  │  phototheque/    │ http │              │
  └────────────────────────┘      │   app.apk        │      │      ↓       │
                                  │                  │◀─────│  appairage   │
                                  │  page /apk       │  QR  │              │
                                  └──────────────────┘      └──────────────┘
```

Trois étapes, trois sections : **§4** construire, **§5** déposer, **§6**
installer.

## 3. Monter la machine de compilation, depuis rien

**Sans aucun `sudo`.** Tout vit dans `~/outils/`. Pour tout défaire, il suffit
d'effacer ce dossier.

```bash
mkdir -p ~/outils && cd ~/outils

# --- JDK 17 (Temurin) ---
curl -L -o jdk17.tar.gz \
  https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse
tar xzf jdk17.tar.gz && mv jdk-17* jdk17 && rm jdk17.tar.gz

# --- Outils en ligne de commande du SDK Android ---
curl -L -o cmdtools.zip \
  https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
mkdir -p ~/outils/android-sdk/cmdline-tools
unzip -q cmdtools.zip -d /tmp/ct
mv /tmp/ct/cmdline-tools ~/outils/android-sdk/cmdline-tools/latest
rm cmdtools.zip

# --- Composants du SDK ---
export JAVA_HOME=~/outils/jdk17 ANDROID_HOME=~/outils/android-sdk
yes | ~/outils/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses
~/outils/android-sdk/cmdline-tools/latest/bin/sdkmanager \
    "platform-tools" "platforms;android-34" "build-tools;34.0.0"
```

**Vérification — les trois doivent répondre :**

```bash
~/outils/jdk17/bin/java -version          # doit afficher 17
ls ~/outils/android-sdk/platforms         # doit contenir android-34
ls ~/outils/android-sdk/platform-tools/adb
```

Gradle **n'est pas** à installer : le dépôt contient `android/gradlew`, qui
télécharge tout seul la version qu'il faut (8.7) au premier lancement.

État connu au 2026-09-21 : JDK Temurin 17.0.20.1, `build-tools;34.0.0`,
`platforms;android-34`.

## 4. Construire et tester

```bash
cd ~/dev/phone_camera_import/android

# Les tests unitaires (84 au 2026-09-21)
JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest

# L'APK de débogage
JAVA_HOME=~/outils/jdk17 ./gradlew assembleDebug
# → app/build/outputs/apk/debug/app-debug.apk
```

> **⚠️ `./gradlew test --tests "…"` échoue sur ce projet.** Il faut écrire
> `./gradlew testDebugUnitTest --tests "…"`. La tâche `test` agrège plusieurs
> variantes et refuse le filtre.

Un rapport lisible est écrit dans
`android/app/build/reports/tests/testDebugUnitTest/index.html`.

## 5. Déposer l'APK sur le NUC

```bash
cd ~/dev/phone_camera_import
./deploy/envoyer-apk.sh                  # compile puis envoie
./deploy/envoyer-apk.sh --sans-compiler  # envoie l'APK déjà construit
```

Le script :

1. compile (sauf `--sans-compiler`) ;
2. lit la version **dans l'APK produit** avec `aapt2` — pas dans le fichier
   Gradle, qui décrirait la source et non le binaire ;
3. calcule l'empreinte SHA-256 ;
4. copie sous un nom temporaire, puis **recalcule l'empreinte à l'arrivée** ;
5. ne met le fichier en place que si les deux empreintes coïncident ;
6. écrit l'étiquette `app.apk.infos.json` à côté.

**Le service n'a pas besoin d'être redémarré** : il relit le fichier à chaque
requête.

Envoyer vers une autre machine :

```bash
NUC=izquierdo@192.168.1.30 ./deploy/envoyer-apk.sh
```

Vérifier sur place :

```bash
ssh izquierdo@192.168.1.21 'ls -la ~/.local/share/phototheque/ && \
    cat ~/.local/share/phototheque/app.apk.infos.json'
```

## 6. Installer sur le téléphone

Trois voies. **La première est la bonne au quotidien** ; les deux autres
servent au développement.

### 6a. Depuis la page d'administration — aucun câble

1. Sur le téléphone, ouvrir `https://IZQUIERDO-NUC.local:8787/`
2. Le navigateur **avertit que le certificat n'est pas reconnu**. C'est normal :
   il est auto-signé. Passer outre.
3. Saisir l'identifiant et le mot de passe d'administration.
4. Section « Application Android » → **Télécharger l'application**.
5. Android demande d'autoriser l'installation depuis cette source
   (« Installer des applications inconnues » pour le navigateur). Accepter.
6. Ouvrir le fichier téléchargé, installer.

### 6b. Par câble USB (adb)

Activer d'abord le mode développeur : **Réglages → À propos du téléphone →
appuyer 7 fois sur « Numéro de build »**, puis **Options pour développeurs →
Débogage USB**.

```bash
~/outils/android-sdk/platform-tools/adb devices     # accepter l'empreinte RSA
~/outils/android-sdk/platform-tools/adb install -r \
    ~/dev/phone_camera_import/android/app/build/outputs/apk/debug/app-debug.apk
```

> **⚠️ Ce poste n'a aucune règle udev Android.** `adb devices` peut afficher
> `no permissions` au lieu du téléphone. Le corriger demande un `sudo` dans un
> vrai terminal (le canal `!` n'a pas de TTY). La voie 6c l'évite entièrement.

### 6c. Débogage sans fil — ni câble, ni udev, ni sudo

Android 11 et plus. **Options pour développeurs → Débogage sans fil →
Associer l'appareil avec un code**.

```bash
~/outils/android-sdk/platform-tools/adb pair 192.168.1.17:37123   # port d'APPAIRAGE
~/outils/android-sdk/platform-tools/adb connect 192.168.1.17:42815 # port de CONNEXION
~/outils/android-sdk/platform-tools/adb install -r …/app-debug.apk
```

Les deux ports sont **différents** et changent à chaque fois. Celui de
l'appairage est dans la fenêtre du code ; celui de la connexion est sur l'écran
principal du débogage sans fil.

### Voir les traces de l'application

```bash
~/outils/android-sdk/platform-tools/adb logcat --pid=$(
  ~/outils/android-sdk/platform-tools/adb shell pidof fr.izquierdo.phototheque)
```

## 7. Appairer le téléphone au serveur

1. Sur un ordinateur, ouvrir `https://IZQUIERDO-NUC.local:8787/pair`
   (identifiants d'administration demandés).
2. La page propose une **date « à partir de »** : les médias antérieurs ne
   seront jamais envoyés. C'est le réglage le plus important de l'appairage.
3. Lancer l'application sur le téléphone, scanner le QR.
4. Appuyer sur **Sauvegarder maintenant**.

**Le QR n'est valable que 10 minutes s'il n'est jamais scanné.** Passé ce
délai, recharger `/pair` en produit un nouveau. Le premier usage réel le
confirme définitivement.

Le QR contient l'adresse du serveur, un jeton d'appareil **et l'empreinte du
certificat**. L'application n'acceptera plus que ce certificat-là : c'est ce
qui rend le HTTPS auto-signé réellement sûr ici.

## 8. Vérifier que ça marche

Sur le téléphone, après une synchro :

- l'accueil affiche **« Sauvegardé aujourd'hui »**, sans bandeau ;
- **« Voir le détail »** liste les dossiers réellement trouvés, avec leur
  nombre de médias, et signale en rouge ceux qui sont suivis mais introuvables.

Sur le NUC :

```bash
ssh izquierdo@192.168.1.21 'ls /media/izquierdo/Famille/Photos/2026/'
ssh izquierdo@192.168.1.21 'journalctl -u phototheque -n 50 --no-pager'
```

Suivre une synchro en direct :

```bash
ssh izquierdo@192.168.1.21 'watch -n5 "du -sh /media/izquierdo/Famille/incoming; \
    find /media/izquierdo/Famille/incoming -type f | wc -l"'
```

Les fichiers atterrissent d'abord dans `incoming/<session>/`. Ils ne sont
rangés qu'au **`commit`**, à la toute fin.

## 9. Dépannage

### « La sauvegarde a échoué » alors que tout est arrivé

**Le défaut le plus déroutant, constaté le 2026-09-21.** Le client HTTP est
construit sans délai explicite, donc avec les **10 secondes par défaut**
d'OkHttp. Or trier une grosse session peut demander vingt minutes : le
téléphone raccroche, affiche un échec, et laisse le compteur sur « Jamais
sauvegardé » — pendant que le serveur range tout parfaitement.

**Comment trancher :** regarder le NUC, pas le téléphone.

```bash
ssh izquierdo@192.168.1.21 'find /media/izquierdo/Famille/incoming -type f | wc -l'
```

Si ce nombre **diminue**, le serveur travaille. Ne relancez rien, ne fermez
rien : attendez.

Corrigé par le lot 1 bis
([spec](superpowers/specs/2026-09-21-app-android-lot1bis-synchro-observable-design.md)).

### Rien ne se passe pendant deux minutes au démarrage d'une synchro

Normal aujourd'hui : l'application calcule l'empreinte SHA-256 de tous les
candidats **avant** de pouvoir demander quoi envoyer. Mesuré à **2 min 08 s**
le 21/09. Rien ne part sur le réseau pendant ce temps. Le lot 1 bis découpe en
paquets et affiche la phase.

### La synchro s'arrête quand j'éteins l'écran

Normal aujourd'hui : il n'y a ni service de premier plan ni `WorkManager`. La
synchro vit dans l'activité. **Gardez l'application affichée** jusqu'à la fin.
Corrigé par le lot 1 bis.

### Un dossier suivi reste à zéro

`Movies/WhatsApp` n'existe pas sur tous les téléphones : WhatsApp récent range
sous `Android/media/com.whatsapp/…`, que MediaStore ne présente pas sous ce
nom. L'écran **« Voir le détail »** le dit en rouge. Au lot 1, les trois
dossiers suivis sont codés en dur dans `ModeleAccueil.kt` ; le choix dans
l'application arrive au lot 2.

### « Serveur introuvable — vous n'êtes probablement pas chez vous »

Trois causes possibles, et l'application ne sait pas encore les distinguer
(issue #23) :

1. le téléphone n'est pas sur le Wi-Fi de la maison ;
2. le service est arrêté sur le NUC ;
3. **le certificat du NUC a changé** — l'épinglage refuse alors la connexion,
   et il faut réappairer avec un nouveau QR.

### « Cet appareil a été révoqué »

Le jeton ne redeviendra jamais valable. Scanner un nouveau QR sur `/pair`.

### Le téléphone n'apparaît pas dans `adb devices`

Voir §6b et §6c : ce poste n'a pas de règles udev. Le débogage sans fil évite
le problème.

### `?` sur l'icône réseau du NUC

**Ce n'est pas une panne du service photo.** C'est NetworkManager en
`CONNECTED_SITE` : le LAN fonctionne, Internet non. Le service n'a jamais
besoin d'Internet.

```bash
journalctl -b -1 | grep "NetworkManager state is now"
```

### La page d'admin dit « Aucune application déposée »

L'APK n'a jamais été envoyé, ou l'envoi a échoué. Relancer
`./deploy/envoyer-apk.sh` depuis le poste de développement.

## 10. Où est quoi

| Chemin | Contenu |
|---|---|
| `android/` | Le code de l'application |
| `android/app/src/main/kotlin/…/ui/` | Les écrans (Compose) |
| `android/app/src/main/kotlin/…/synchro/` | Horizon, sélection, orchestration |
| `android/app/src/main/kotlin/…/reseau/` | Client HTTP, épinglage, découverte mDNS |
| `android/app/build/outputs/apk/debug/app-debug.apk` | Le binaire produit |
| `deploy/envoyer-apk.sh` | L'envoi vers le NUC |
| `phototheque/apk.py` | Lecture de l'APK déposé, côté serveur |
| `~/outils/jdk17`, `~/outils/android-sdk` | L'outillage (poste de dev) |
| `~/.local/share/phototheque/app.apk` | L'APK déposé (NUC) |

**Documents liés :**

- [`CONTRAT-APP.md`](CONTRAT-APP.md) — le protocole exact entre l'app et le
  serveur, avec des exemples capturés sur un échange réel
- [`DEPLOIEMENT.md`](DEPLOIEMENT.md) — le serveur
- [`superpowers/specs/2026-09-18-application-android-design.md`](superpowers/specs/2026-09-18-application-android-design.md)
  — pourquoi l'application est faite ainsi
