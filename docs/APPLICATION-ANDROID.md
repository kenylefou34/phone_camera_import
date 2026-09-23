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

**Il trouve le NUC tout seul.** L'adresse n'est plus écrite en dur : le script
résout `IZQUIERDO-NUC.local` en mDNS — comme le fait l'application — puis
**sonde** l'adresse obtenue avant de la retenir, parce qu'une résolution qui
aboutit ne prouve pas que la machine répond. À défaut, il retombe sur
`192.168.1.21`.

Huit essais espacés le séparent d'un abandon : le lien WiFi du NUC bat
(mesuré le 23/09 : environ 20 s joignable puis 35 s injoignable), et un essai
unique renoncerait sur un creux alors que la machine est allumée.

Trois surcharges, selon le besoin :

```bash
NUC=izquierdo@192.168.1.30 ./deploy/envoyer-apk.sh   # forcer une machine
NUC_HOTE=autre-nuc.local   ./deploy/envoyer-apk.sh   # autre nom mDNS
NUC_REPLI=192.168.1.42     ./deploy/envoyer-apk.sh   # autre repli
```

Si le script annonce que le nom **résout** mais que le port ne répond pas,
c'est le lien radio qui lâche, pas un problème de nom — voir `CLAUDE.md`.

Vérifier sur place :

```bash
ssh izquierdo@192.168.1.21 'ls -la ~/.local/share/phototheque/ && \
    cat ~/.local/share/phototheque/app.apk.infos.json'
```

## 6. Installer sur le téléphone

Trois voies. **La première est la bonne au quotidien** ; les deux autres
servent au développement.

### 6a. Depuis la page d'administration — aucun câble

1. Sur le téléphone, ouvrir **`https://<IP-DU-NUC>:8787/`** — par exemple
   `https://192.168.1.31:8787/`.

   > **⚠️ NE PAS utiliser `https://IZQUIERDO-NUC.local:8787/` depuis le
   > téléphone.** Les navigateurs Android **ne résolvent pas le mDNS** : Chrome
   > n'a pas de résolveur `.local` pour sa barre d'adresse, et l'URL échoue
   > même quand le serveur répond parfaitement. Constaté le 23/09.
   >
   > L'**application**, elle, n'a pas ce problème : elle passe par
   > `NsdManager`, l'API mDNS native d'Android, qui fonctionne. Seul le
   > navigateur est concerné.
   >
   > Pour connaître l'IP du moment, depuis le poste de développement :
   > `avahi-resolve -4 -n IZQUIERDO-NUC.local`

2. Le navigateur avertit **deux fois** : le certificat est auto-signé, **et**
   l'adresse IP ne correspond pas au nom qu'il porte. Les deux sont normaux
   ici. Passer outre.
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

## 8. Les réglages : dossiers, dates, automatique, désappairage

Le lot 2 ajoute trois écrans, atteints depuis l'accueil par un bouton
**Réglages**, puis un bouton par écran. Le bouton retour du système ramène de
chacun d'eux à Réglages, et de Réglages à l'accueil.

| Écran | Depuis Réglages | Ce qu'il montre |
|---|---|---|
| **Dossiers** | « Dossiers à sauvegarder » | l'arborescence des dossiers du téléphone, balayée depuis MediaStore **à l'ouverture de l'écran** (pas depuis la dernière synchro — voir la recette, étape 1). Une case par ligne, trois choix au dépli : « Ce dossier seulement », « Ce dossier et ses sous-dossiers », « Ne pas sauvegarder ». Case à moitié pleine si seule une partie de la descendance est cochée. Les chaînes de dossiers vides à enfant unique (ex. `Android/media/com.whatsapp/…`) sont repliées sur une seule ligne. Bouton « voir » pour un aperçu à la demande, sans vignette sur la liste elle-même. |
| **Sauvegarde** (« Quand sauvegarder ») | « Quand sauvegarder » | les deux bornes de la fenêtre de dates, l'interrupteur « Sauvegarder automatiquement » (efface et grise la borne de fin, en le disant), et deux compteurs distincts : médias antérieurs à la date de début (neutre) et médias postérieurs à la date de fin (avertissement — le signal d'une borne oubliée). |
| **Appareil** (« Cet appareil ») | « Cet appareil » | l'état de l'appairage et le bouton « Désappairer ce téléphone », avec une confirmation qui annonce ce que le prochain appairage relira réellement (voir plus bas). |

### Baisser la date de début : l'ordre de reprise

Baisser la date « Depuis » propose de nouveau, **une seule fois**, les médias
plus anciens que l'horizon déjà connu de chaque dossier coché — sans jamais
faire reculer ce que le serveur retient (la monotonie de l'horizon, voir
[`CONTRAT-APP.md`](CONTRAT-APP.md) §5). Relancer une deuxième fois sans avoir
rechangé la date ne repropose rien : c'est la preuve que la reprise ne
s'applique qu'une fois.

**La REMONTER ne déclenche aucune reprise**, et c'est voulu : passer de 2019 à
2024 est le geste de qui veut alléger, pas relire toute la bibliothèque.

**Ce que la remonter fait, en revanche** : les médias d'un dossier situés
entre son horizon et la nouvelle date de début ne partent plus, et
l'application **gèle l'horizon de ce dossier** tant que c'est le cas. Rien
n'est perdu — la tranche redevient proposable dès que la date redescend — mais
l'horizon de ce dossier n'avance plus, donc ses médias sont réanalysés à
chaque sauvegarde. Si une sauvegarde vous paraît longue sans rien envoyer,
c'est la première chose à regarder : effacer la date de début remet tout
d'aplomb.

### Deux gestes qui décochent plus que la ligne touchée

- **« Ne pas sauvegarder » sur un dossier à la case à moitié pleine** décoche
  **toute sa descendance**, et la ligne dépliée nomme d'abord les
  sous-dossiers concernés. Sans cela, ce choix n'aurait strictement aucun
  effet : la case est à moitié pleine parce que ce sont des enfants, et non ce
  dossier-là, qui sont cochés.
- **Aucun dossier coché du tout** : l'accueil le dit en bandeau, et la
  sauvegarde n'est plus comptée comme une réussite — sans quoi le compteur
  resterait au vert pendant que plus rien ne part.

### « Interrompre » ne déprogramme pas la sauvegarde automatique

Le bouton annule les deux files, la manuelle et l'automatique, puis
**reprogramme** l'automatique si l'interrupteur est coché — avec six heures de
délai, pour ne pas relancer aussitôt ce qu'on vient d'arrêter. La prochaine
passe automatique glisse donc d'autant. Sans cette reprogrammation, un seul
appui aurait déprogrammé la sauvegarde automatique pour de bon, l'interrupteur
restant affiché « actif ».

### Le désappairage : ce que dit la confirmation

Désappairer efface l'état local **inconditionnellement**, même si le serveur
est injoignable — c'est justement le cas d'usage (certificat changé, NUC
injoignable). Le serveur est prévenu **au mieux** ; son échec est signalé à
l'écran, jamais bloquant.

**Après un réappairage, le serveur repart de la date du jour** : il pose
`horizon_initial` à la date du jour à **chaque** appairage
(`phototheque/devices.py:94`), jamais à l'historique complet, même pour un
réappairage du même téléphone. C'est pourquoi la confirmation de désappairage
annonce explicitement ce qui sera relu au prochain appairage : si une date de
début est déjà posée dans « Quand sauvegarder » (elle survit au
désappairage — ce n'est pas un réglage lié à un serveur), c'est elle qui
commande ; sinon, il faudra la poser après coup pour retrouver les médias plus
anciens que le jour du réappairage.

### Ce que « toutes les 6 h » veut vraiment dire

La sauvegarde automatique n'est **pas un réveil à heure fixe** :

- au plus une fois par tranche de 6 h, et seulement quand les conditions sont
  réunies (WiFi non facturé **et** téléphone en charge) ;
- Android **regroupe** ces réveils (mode Doze) : le délai peut glisser à 7 ou
  8 h si le téléphone dort, **jamais se déclencher plus tôt** ;
- sans réseau non facturé ou sans charge, l'échéance passe sans rien faire —
  ce n'est pas un échec, juste un tour sauté ;
- « Synchroniser maintenant » reste disponible à tout moment et ignore ces
  contraintes.

**En pratique : une passe par nuit, au branchement du téléphone à la maison.**
Le compteur « dernière sauvegarde » de l'accueil reste affiché même en
automatique — c'est lui qui révèle un automatique qui tournerait dans le vide
(WiFi de la maison jamais retrouvé, par exemple).

`ExistingPeriodicWorkPolicy.KEEP` fait qu'ouvrir cet écran ne reprogramme
**pas** le travail périodique s'il existe déjà : le reprogrammer à chaque
ouverture remettrait le compteur des 6 h à zéro, et la passe n'aurait jamais
lieu sur un téléphone qu'on ouvre souvent. Un réappairage, en revanche,
reprogramme réellement le travail si l'automatique était coché — sinon
l'interrupteur resterait affiché actif sans plus rien planifier (voir la
recette, étape 14).

## 9. Recette de validation sur un vrai téléphone

**Rien de ce qui suit n'est couvert par un test automatique.** Le projet n'a
aucun test d'instrumentation Android : `WorkManager`, le service de premier
plan, les notifications, Compose et `VerrouSynchro` ne sont vérifiés que par
lecture. C'est cette recette qui en tient lieu — à dérouler telle quelle, dans
cet ordre, qui suit un usage réel plutôt que la liste des fonctions à tester.

**Point de départ :** l'application installée (§6) et appairée (§7), **avant**
la toute première synchronisation.

**Deux limites restent ASSUMÉES** (issue #33, héritées du lot 1 bis) : ne pas
les prendre pour des régressions de cette recette.
- Interrompre pendant l'envoi d'une grosse vidéo n'arrête pas ce
  téléversement-là ; seuls les fichiers suivants s'arrêtent.
- L'écran reste figé pendant l'envoi d'une grosse vidéo.

1. **Ouvrir Réglages → Dossiers avant toute synchronisation.** L'écran doit se
   remplir tout seul, pas rester vide.
   *Pourquoi :* cet écran balaie MediaStore lui-même à l'ouverture — il ne
   dépend plus de `dossiersVus`, qui vaut `null` tant qu'aucune synchro n'a
   jamais eu lieu. Un test JVM ne peut pas vérifier ce balayage : il n'a pas
   de MediaStore.

2. **Cocher `Android` en « ce dossier et ses sous-dossiers ».** Vérifier que
   la chaîne `Android/media/com.whatsapp/…` apparaît **repliée sur une seule
   ligne**, avec un compte de médias non nul.
   *Pourquoi :* le repli des chaînes sans média à enfant unique n'est prouvé
   par les tests que sur des chemins fabriqués ; seul un vrai téléphone
   WhatsApp a la profondeur de dossiers qui justifie ce repli.

3. **Cocher `Pictures` en « ce dossier et ses sous-dossiers », puis entrer
   dedans.** Les sous-dossiers doivent apparaître **cochés**, et leur ligne
   doit **nommer le parent responsable** (« Pris par « Pictures »… ») plutôt
   que d'offrir les trois choix habituels.
   *Pourquoi :* décocher un dossier hérité ne ferait rien — l'écran doit le
   dire en clair au lieu de proposer un choix qui ne changerait rien.

4. **Vérifier qu'un dossier dont un seul enfant est coché affiche la case à
   moitié pleine**, et non pleine ni vide.
   *Pourquoi :* `TriStateCheckbox` est un rendu Compose, invisible à un test
   JVM ; seul `Choix.etat` (la valeur `PARTIELLE`) l'est.

5. **Appuyer sur « voir » sur un dossier avec des médias directs.** Une grille
   d'aperçu doit s'ouvrir. Vérifier aussi qu'aucun bouton « voir » n'apparaît
   sur un dossier sans média direct (seulement des sous-dossiers).
   *Pourquoi :* le décodage de vignettes est une opération Android réelle,
   hors de portée de la JVM.

6. **Vérifier qu'aucune alerte rouge « Introuvables » n'apparaît** pour une
   coche récursive normale (ex. `Pictures` coché récursif, dont le seul
   contenu réel vient de `Pictures/WhatsApp`).
   *Pourquoi :* c'est exactement le faux positif que `Choix.introuvables`
   existe pour éliminer — une coche récursive qui fonctionne parfaitement ne
   doit jamais être signalée comme en échec.

7. **Dans Réglages → Sauvegarde, poser une date de fin dans le passé.**
   Vérifier que l'écran annonce séparément les médias **antérieurs** à la
   date de début (message neutre) et **postérieurs** à la date de fin
   (avertissement).
   *Pourquoi :* mélanger les deux noierait le seul signal qui compte — une
   date de fin oubliée — sous le nombre, bien plus grand en pratique, des
   vieux médias volontairement laissés de côté.

8. **Inverser les deux dates** (début après fin). Vérifier que le message dit
   l'inversion **sans prétendre que rien ne sera sauvegardé**.
   *Pourquoi :* les ancrages de fenêtre sont volontairement asymétriques
   (UTC+14 pour le début, UTC-12 + 1 jour pour la fin), donc une inversion
   d'un seul jour laisse encore passer une bonne partie d'une journée —
   promettre « aucun média » serait parfois faux.

9. **Poser une date de début ancienne (ex. 2019) et lancer.** Vérifier que des
   médias anciens sont proposés — c'est l'ordre de reprise. **Laisser finir,
   relancer immédiatement** : vérifier que **rien n'est reproposé** la
   deuxième fois.
   *Pourquoi :* c'est le cœur du lot 2, exercé pour de vrai avec un
   `CoroutineWorker`, MediaStore et un aller-retour réseau réels — les tests
   JVM ne vérifient que les fonctions pures avec des réglages fabriqués.

10. **Cocher « Sauvegarder automatiquement ».** Vérifier que la date de fin
    disparaît, que l'application le **dit**, et que le champ reste **visible,
    grisé** (pas caché).
    *Pourquoi :* le grisage (opacité réduite) est un détail de rendu Compose ;
    sans le champ sous les yeux, impossible de voir *pourquoi* la borne a
    disparu.

11. **Brancher le téléphone sur le WiFi de la maison, le laisser en charge une
    nuit.** Vérifier au matin que « dernière sauvegarde » s'est mise à jour
    **sans intervention**.
    *Pourquoi :* c'est `PeriodicWorkRequest` et le mode Doze pour de vrai —
    rien dans ce projet ne peut simuler le planificateur d'Android.

12. **Pendant que l'automatique tourne (ou juste après l'avoir déclenché),
    lancer une synchro manuelle.** Vérifier qu'un **seul** avancement est
    affiché (pas deux qui se mélangent), et que le bouton « Interrompre »
    arrête bien celle qui tourne.
    *Pourquoi :* `VerrouSynchro` n'est exercé par **aucun test** — c'est la
    seule protection entre deux `WorkManager` réels (la file manuelle et la
    file automatique) qui pourraient démarrer ensemble.

13. **Couper le WiFi, puis désappairer depuis Réglages → Appareil.** Vérifier
    que l'application revient à l'écran de scan **malgré le serveur
    injoignable**, et qu'elle **dit** que le serveur n'a pas pu être prévenu.
    *Pourquoi :* c'est le cas d'usage réel du désappairage (certificat changé,
    NUC injoignable) — un vrai échec réseau, pas un mensonge de test.

14. **Réappairer.** Vérifier que les dossiers cochés ont **survécu** au
    désappairage, et — si l'automatique était coché avant de désappairer —
    qu'il est **réellement reprogrammé** (pas seulement réaffiché coché).
    *Pourquoi :* les réglages persistent volontairement (ils ne sont pas liés
    à un serveur), mais la reprogrammation de `WorkManager` est un appel de
    code neuf, sans test d'instrumentation pour le confirmer.

15. **Après ce réappairage, vérifier que l'accueil n'affiche PAS « sauvegardé
    il y a N heures ».** Le compteur doit avoir été effacé.
    *Pourquoi :* une ancienne réussite ne dit plus rien du nouveau serveur —
    l'afficher serait une fausse réassurance, pire qu'une fausse alerte
    puisqu'elle éteint le seul filet du projet contre les pannes muettes.

16. **Cocher « Sauvegarder automatiquement », revenir à l'accueil et le
    regarder sans rien toucher.** Le bouton « Sauvegarder maintenant » doit
    rester **actif**, et l'accueil ne doit afficher ni barre de progression,
    ni « Sauvegarde en attente… », ni « Interrompre ».
    *Pourquoi :* un travail périodique reste `ENQUEUED` entre deux passes,
    pour toujours. L'écran en tirait une attente permanente et grisait le
    bouton définitivement. Rien, côté JVM, ne peut voir un bouton grisé.

17. **Décocher tous les dossiers** (Réglages → Dossiers). L'accueil doit
    afficher le bandeau « Aucun dossier n'est sélectionné ». Lancer une
    sauvegarde : le compteur de jours ne doit **pas** repasser à « Sauvegardé
    aujourd'hui ». Recocher ensuite ce qu'il faut.
    *Pourquoi :* c'est la panne muette la plus facile à déclencher depuis que
    les dossiers se choisissent — une sauvegarde « réussie » à zéro média,
    verte, indéfiniment.

**Si c'est la toute première fois que l'application tourne sur un appareil**,
la recette du lot 1 bis (tâche 10 de
[`superpowers/plans/2026-09-21-app-android-lot1bis.md`](superpowers/plans/2026-09-21-app-android-lot1bis.md),
18 étapes) reste la référence la plus détaillée pour ce que celle-ci ne
redemande pas explicitement : le contenu exact de la notification, la reprise
après une coupure subie, le bouton d'arrêt de la notification elle-même.

## 10. Vérifier que ça marche

Sur le téléphone, après une synchro :

- l'accueil affiche **« Sauvegardé aujourd'hui »**, sans bandeau ;
- **« Voir le détail »** liste les dossiers réellement trouvés, avec leur
  nombre de médias, et signale en rouge ceux qui sont suivis mais introuvables.
- **L'accueil lui-même** annonce les dossiers qu'une coche « et ses
  sous-dossiers » vient d'embarquer pour la première fois. Ce rappel est là
  pour qu'on n'ait rien à surveiller : il ne se cache pas derrière « Voir le
  détail ».

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

## 11. Dépannage

### « La sauvegarde a échoué » alors que tout est arrivé

**Le défaut le plus déroutant, constaté le 2026-09-21.** Le client HTTP est
construit sans délai explicite, donc avec les **10 secondes par défaut**
d'OkHttp. Or trier une grosse session peut demander **plus d'une heure** —
1 h 02 mesurée le 21/09 pour 971 fichiers et 14 Go. Le téléphone raccroche,
affiche un échec, et laisse le compteur sur « Jamais sauvegardé » — pendant que
le serveur range tout parfaitement.

Pire : ce commit-là **ne laisse aucune trace dans `journalctl`**. uvicorn
journalise une requête quand il y répond ; le client étant parti, la ligne
n'est jamais écrite. Chercher `sync/commit` dans le journal ne prouve donc
rien.

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
nom. L'écran **« Voir le détail »** le dit en rouge. Depuis le lot 2, le choix
n'est plus figé : ouvrir **Réglages → Dossiers**, cocher `Android` en « ce
dossier et ses sous-dossiers » (§8) prend cette chaîne, repliée sur une seule
ligne.

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

## 12. Où est quoi

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
