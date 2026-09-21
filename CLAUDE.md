# CLAUDE.md — phone_camera_import

Point de reprise pour les sessions Claude Code. **Documenter/commenter en français**
(le mainteneur débute en Python).

## Le projet
Système d'import de médias : téléphone → NUC → bibliothèque rangée par type et
date (`Photos|Videos/ANNÉE/"MM MOIS"`). Refonte en cours sur la branche `dev`.

Vision : **Phase 1** import (trieur + service + app) ; **Phase 2** consultation web
+ revue visuelle (doublons, floues/rafales, re-datation) ; **Phase 3** visages ;
**Phase 4** génération (livre photo…).

## État actuel (2026-09-18, soir)
- ✅ **Trieur `mediasort/`** (Python, stdlib + exiftool/ffmpeg) : range par vraie
  date (métadonnées > nom > système > `_A_TRIER/`), anti-doublon par catalogue
  SQLite d'empreintes. Testé.
- ✅ **Catalogue complet** : `~/mediasort_catalog.db` sur le NUC = **44 669 médias
  uniques** (sur 59 884 fichiers → ~15 200 doublons dans la biblio, cf. issue #4).
- ✅ **Backlog WhatsApp trié** (4 rangés, 92 doublons évités) ; bruit nettoyé.
- ✅ **Service `phototheque/`** (sous-projet 2, renommé depuis `mediaserve` le 17/09) : FastAPI, appairage QR, handshake
  anti-doublon, upload, commit (bilan détaillé), page d'admin (appareils +
  camembert disque), mDNS/Avahi, systemd + Docker. Validé sur le NUC.
- ✅ **Déployé en service permanent** (issue #11) : `phototheque.service` actif et
  `enabled` sur le NUC depuis le 2026-09-14, 0 redémarrage. `/` et `/pair`
  répondent, `/status` exige l'authentification.
- ✅ **Pré-filtre par signature rapide** (issue #9) : le trieur évite la lecture
  intégrale d'un fichier dont la signature est inconnue (~1000× plus rapide sur
  une vidéo de 3 Go : 28,6 s → 0,028 s).
- ✅ **Empreinte calculée pendant la copie** (issue #14) : un fichier rangé n'est
  plus traversé que 2 fois au lieu de 3 (mesuré sur le NUC, vidéo de 3,6 Gio :
  47,9 s → 34,9 s, -27 %).
- ✅ **Appairage durci** : un QR affiché crée un appairage *en attente* qui
  expire au bout de 10 min s'il n'est jamais utilisé (le premier usage le
  confirme définitivement) ; `/pair` fait le ménage à chaque visite. La base
  des appareils n'est plus ouverte à l'import du module.
- ✅ **Transport chiffré + admin protégée + horizon de synchro** (issues #3, #10,
  #2) : HTTPS auto-signé épinglable par l'app, mot de passe admin sur `/`,
  `/pair`, `/devices` et la révocation, horizon par (appareil, dossier).
  Adresse : `https://IZQUIERDO-NUC.local:8787/`.
- ✅ **Identifiants d'admin choisis par le mainteneur** : `./deploy/identifiants.sh`
  change identifiant ET mot de passe, sans sudo ni redémarrage (relus à chaque
  requête). Fichier `~/.config/phototheque/utilisateur` absent = `admin`.
- ✅ **Durcissement du 18/09** : `/docs`, `/redoc` et `/openapi.json` étaient
  **ouverts sans mot de passe** sur le NUC — fermés (404), rouvrables par
  `DOCS_PUBLIQUES=1` en développement.
- ✅ **Envois par blocs** (issue #21) : `/sync/upload` ne charge plus le fichier
  entier en mémoire (300 Mio : pic de 311 Mio → 13,5 Mio). Sans ça, la première
  vidéo de plus de 2 Gio faisait tuer le service par le noyau, en boucle.
- ✅ **Limitation des essais** (issue #19) : 5 essais libres par machine, puis
  une attente qui double (2, 4, 8 s…) plafonnée à 60 s, et surtout un refus
  **sans calcul d'empreinte** (~38 ms → ~2 ms). Compteur en mémoire : un
  `systemctl restart phototheque` le remet à zéro si on se bloque soi-même.
  **243 tests** côté serveur.
- ✅ **Contrat serveur de l'app écrit** (issue #15) : `docs/CONTRAT-APP.md`,
  exemples **capturés sur un échange réel**. La section 6 de la spec y renvoie.
- ✅ **Sous-projet 3, lot 1 de l'application Android ÉCRIT** (issue #12) :
  Kotlin natif sous `android/`, **84 tests**, APK de débogage produit. Conception :
  `docs/superpowers/specs/2026-09-18-application-android-design.md` ; plan :
  `docs/superpowers/plans/2026-09-18-app-android-lot1.md`.
  **Jamais essayé sur un vrai téléphone** — c'est la tâche 15 du plan, et elle
  reste à faire (voir la section REPRISE).
  Outillage local : JDK 17 et SDK Android sous `~/outils/`, sans sudo.
  Lancer les tests : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest`
  (⚠️ `./gradlew test --tests` échoue : utiliser `testDebugUnitTest --tests`).
- Déploiement : `./deploy/install.sh` — voir `docs/DEPLOIEMENT.md`.
- Spécs : `docs/superpowers/specs/` — plans : `docs/superpowers/plans/`.

## ⚠️ REPRISE — première chose à faire

**Essayer l'application sur un vrai téléphone** — tâche 15 du plan
`docs/superpowers/plans/2026-09-18-app-android-lot1.md`. Tout le reste du lot 1
est écrit, relu et corrigé ; rien n'a jamais tourné sur un appareil.

```bash
cd ~/dev/phone_camera_import/android
JAVA_HOME=~/outils/jdk17 ./gradlew assembleDebug
~/outils/android-sdk/platform-tools/adb install -r app/build/outputs/apk/debug/app-debug.apk
```

(Activer d'abord le débogage USB : Réglages → À propos → 7 appuis sur « Numéro
de build », puis Options pour développeurs → Débogage USB.)

**À vérifier en premier**, car deux fonctions en dépendent (le bandeau
d'avertissement ET l'avancée du compteur) : une synchro avec la permission
accordée doit afficher « Sauvegardé aujourd'hui » et **aucun** bandeau. Sinon,
c'est `Depot.accesRefuse()` qu'il faut regarder.

**Ce que l'essai ne pourra PAS prouver :** l'étape 5 (régénérer le certificat du
NUC pour vérifier l'épinglage) affiche le même écran que « couper le Wi-Fi ».
C'est l'issue **#23**, laissée ouverte sciemment.

**Les cinq pannes doivent produire cinq messages distincts** — c'est le fil
conducteur de tout le lot : pas à la maison (silencieux), appareil révoqué,
permission retirée, serveur en erreur de rangement, aucun dossier trouvé.

**Après l'essai** : issue #23 (épinglage), puis lot 2 (choix des dossiers dans
l'app) — attention, le lot 2 supprime la protection accidentelle qui masque
aujourd'hui le cas du dossier vide.

**Décision en suspens depuis le 17/09, jamais tranchée** : deux sauvegardes
dorment sur le NUC, créées avant des opérations lourdes et devenues inutiles si
tout va bien. Les garder ou les supprimer est au mainteneur, pas à un agent.
- `~/mediasort_catalog.db.avant-signatures` (12 Mo) — état du catalogue d'avant
  le rattrapage des signatures du 17/09 au matin, qui s'est bien passé.
- `~/phototheque_devices.db.vide-20260917-134451` (16 Ko) — base d'appairage
  vide mise de côté par `install.sh` lors du renommage.

## Feuille de route (issues GitHub)
Prochaine étape : **sous-projet 3 = app Android** (issue #12 : scan QR, scan des
dossiers, client d'upload) — commencer par #15, qui fige le contrat qu'elle
codera en dur. Améliorations/Phase 2 tracées en issues #2 à #10 et #14 à #27
(`gh issue list`). Notamment : #4 doublons existants, #5 floues/rafales,
#6 re-datation, #7 sauvegarde Famille.

**Les constats mineurs différés ne vivent plus dans un journal de session** :
#24 pour le lot Android, **#26 pour le lot serveur** (transport/auth/horizon du
17/09 — ils n'avaient aucune trace jusqu'au 21/09). **#27** porte la moitié
restante du constat C2 de ce lot : le serveur refuse désormais les extensions
qu'il ne sait pas ranger, mais le trieur en ligne de commande les ignore
toujours **sans le moindre compteur** — l'utilisateur ne peut pas savoir. Le seul qui ait *gagné* en
portée depuis son signalement est le court-circuit temporel sur le nom
d'utilisateur, devenu un secret partiel depuis `identifiants.sh`.

Le travail de #2, #3, #10, #14, #15, #19 et #21 est **fait** ; #12 est écrit mais pas éprouvé (#8, #9 et #11 sont fermées), mais
ces quatre-là **apparaissent encore ouvertes sur GitHub** : leurs commits portent
bien `closes #N`, or GitHub ne ferme une issue qu'à la fusion dans la branche par
défaut. Elles se fermeront toutes seules quand **PR #13 (`dev` → `main`)** sera
fusionnée — ce qui reste à faire, de préférence après le déploiement ci-dessus.

## NUC (machine cible)
- `ssh izquierdo@192.168.1.21` (clé configurée, hôte `IZQUIERDO-NUC`, Ubuntu 26.04,
  Python 3.14, 2 cœurs / 3 Go). `sudo` restreint via `/etc/sudoers.d/claude-maint`
  (apt, fsck, mount, smartctl…) ; le reste demande un vrai terminal (le canal `!`
  n'a pas de TTY). **Pas de `curl`** sur le NUC (utiliser python/urllib).
- **PEP 668** : le python système refuse `pip --user` → **venv obligatoire**
  (`~/.venv-server` pour le serveur).
- Disques externes sous `/media/izquierdo/` : **Famille** (NTFS) = bibliothèque
  cible ; **ELEMENTS** (FAT32, réparé) = archive ; **Media** (exfat). Ne jamais
  toucher aux dossiers d'événements curatés (ex. `2022/02 - CANARIAS`).
- WhatsApp enregistré sur le tél : `Pictures/WhatsApp/` (images) + `Movies/WhatsApp/`
  (vidéos) — pas le dump interne de WhatsApp (~99 % "Sent").

## ⚠️ Cas particuliers (ce qui a déjà fait perdre du temps)

**Environnement**
- `hostname -I` sur le NUC renvoie **4 adresses** (1 IPv4 + 3 IPv6), pas une.
  `install.sh` prend la première via `awk '{print $1}'` et tombe aujourd'hui sur
  la bonne — par chance d'ordonnancement, pas par construction.
- Le NUC héberge aussi **Plex** (snap, port 32400) et l'**UPnP de la box est
  activé** : un programme peut s'ouvrir un accès Internet sans prévenir. Voir la
  mémoire `projet-nuc-exposition-reseau`.
- **Audit réseau LAN (fait au démarrage du projet, 2026-09-14)** : le **NAS
  `192.168.1.20` expose du FTP en clair** (ProFTPD) + SMB — identifiants et
  fichiers non chiffrés sur le LAN. Hors périmètre de l'appli photo (appareil
  tiers, non reconfigurable par nous). Détail + inventaire des hôtes : mémoire
  `projet-audit-reseau-lan`.
- Pas de `curl` sur le NUC ; `sudo` exige un vrai terminal (le canal `!` n'a pas
  de TTY) ; PEP 668 impose le venv.
- **Le `?` sur l'icône réseau du NUC ne veut PAS dire que le service photo est
  tombé** (constaté le 2026-09-21). C'est NetworkManager en état
  `CONNECTED_SITE` : « le LAN marche, je n'atteins pas Internet ». Le service
  photo n'a jamais besoin d'Internet, seulement du LAN — un téléphone sur le
  même WiFi le joint normalement pendant tout l'épisode. Redémarrer le NUC pour
  ça ne sert à rien.
  Diagnostic en une commande :
  `journalctl -b -1 | grep "NetworkManager state is now"` — `CONNECTED_GLOBAL` =
  tout va bien, `CONNECTED_SITE` = Internet KO, LAN OK.
  Ce jour-là : lien WiFi **associé sans interruption du 16/09 09:06 au 21/09
  08:56** (zéro événement noyau `wlo2`), aucune mise en veille, aucun trou dans
  le journal ; seules les bascules de connectivité se dégradaient (3 en 16
  jours, puis 6 le 19/09, 11 le 20/09, bloqué en `CONNECTED_SITE` à 03:22:53 le
  21/09). Cause en amont : la box ou le lien opérateur.
  Deux pièges rencontrés en cherchant : `grep "PM: hibernation"` remonte des
  lignes de **démarrage** (`Registered nosave memory`), ce ne sont pas des
  veilles ; et un grep large sur `disconnect|deauthenticat` donne 744 lignes de
  bruit là où le noyau n'en a que quelques-unes de réelles (filtrer sur `wlo2:`).
- **`eno1` (ethernet du NUC) n'a aucun câble** (`cat /sys/class/net/eno1/carrier`
  = 0) : le WiFi est l'unique chemin vers le serveur photo. Un câble le rendrait
  insensible aux aléas radio — action physique, à la main du mainteneur.

**Pièges du serveur**
- **FastAPI publie `/docs`, `/redoc` et `/openapi.json` sans authentification.**
  Ils étaient ouverts sur le NUC jusqu'au 18/09. Fermés (404) ;
  `DOCS_PUBLIQUES=1` les rouvre en développement. **Y repenser à chaque ajout de
  route** : ces chemins n'apparaissent nulle part dans le code.
- L'**authentification HTTP Basic** fait que le navigateur renvoie les anciens
  identifiants tant qu'il n'est pas entièrement fermé. Toujours tester un
  changement d'identifiants en **navigation privée**, sinon on conclut à tort
  que le changement n'a pas pris.
- Une requête **sans identifiants n'est pas un échec** : le navigateur en envoie
  toujours une avant d'afficher sa fenêtre. La compter dans la limitation
  d'essais (#19) bloquerait le mainteneur en navigation normale.
- `charge_appairage()` lit la variable de module `_appairage_en_cours` : elle
  lève si on l'appelle sans passer par `/pair`. Pour un script, utiliser
  directement `pairing.pairing_payload(...)`.
- L'**horizon est décidé par l'application**, pas par le serveur. Un horizon
  avancé au-delà d'un fichier jamais envoyé le perd définitivement et en
  silence. Détaillé dans `docs/CONTRAT-APP.md`, section 5.

**Tests**
- Simuler une machine d'origine : `TestClient(app, client=("192.168.1.50", 1))`.
- Les tests d'app rechargent `config` **puis** `app` (`importlib.reload`) après
  avoir posé les variables d'environnement — sinon les chemins restent ceux de
  l'import initial.
- Un test qui passe du premier coup ne prouve rien. Systématiquement le valider
  **par mutation** : casser volontairement le code et vérifier que c'est bien ce
  test-là qui tombe. Plusieurs faux verts ont été attrapés ainsi le 18/09
  (script absent → code 127, propriétés déjà vraies avant correctif).

**Outillage (ça a déjà coûté une demi-heure chacun)**
- **`pgrep -f "motif"` se trouve lui-même** : la ligne de commande du shell qui
  l'exécute contient le motif. Une boucle `until ! pgrep -f "…"` ne sort donc
  JAMAIS. C'est ce qui a fait croire, le 17/09, qu'un rattrapage de signatures
  tournait encore alors qu'il était fini depuis vingt minutes. Filtrer sur le
  vrai processus (`pgrep -f "python3 -m mediasort"`) ou exclure son propre PID.
- **Chromium est confiné (snap)** : il n'écrit une capture que sous
  `/home/invisart`, et **pas dans un dossier caché**. Viser le répertoire
  scratchpad ou `~/.quelquechose` échoue avec « Permission denied » ou
  « No such file or directory ». Passer par `~/un-dossier-visible/`, puis
  nettoyer.
- **`gh pr edit` est cassé sur ce dépôt** : il interroge l'API « Projects
  classic », supprimée par GitHub, et échoue sans rien modifier. Pour changer le
  titre ou le corps d'une PR, passer par l'API REST :
  `gh api "repos/$REPO/pulls/13" -X PATCH -F body=@fichier.md -f title="…"`.
- **Extrapoler une durée sur un échantillon pris dans l'ordre de la base est
  faux** : 200 médias avaient annoncé 1 h pour le rattrapage des signatures, il
  a pris 16 min (les gros fichiers sont regroupés en tête).

**Conventions**
- Les messages de commit du dépôt sont **sans accents** (sujet et corps).
- `deploy/lib.sh` : ne **jamais** décider à partir d'un pipeline (`| grep -q`
  renvoie 141 sous `pipefail`, ce qui a déjà inversé une décision en production).

## Commandes utiles
```bash
# Tests (local, pytest via pip --user) :
python3 -m pytest -q

# Trieur (sur le NUC) :
python3 -m mediasort --source <dossier> --library /media/izquierdo/Famille \
    --catalog ~/mediasort_catalog.db [--seed --seed-from <dossier>] [--dry-run] [--clean-noise]

# Compléter les signatures d'un ancien catalogue (réactive le pré-filtre) :
python3 -m mediasort --catalog ~/mediasort_catalog.db --backfill-signatures

# Serveur (sur le NUC) — installation ET mise à jour, idempotent :
cd ~/phone_camera_import && git pull && ./deploy/install.sh
# puis https://IZQUIERDO-NUC.local:8787/ (admin, identifiant "admin") et /pair (QR)
#   (nuc.local ne résout PAS : la machine s'annonce en <hostname>.local)
#   (le navigateur avertit au premier accès : certificat auto-signé, normal)
#   (mot de passe affiché une seule fois par install.sh)
# Choisir/changer identifiant ET mot de passe d'admin (sans sudo ni redémarrage) :
./deploy/identifiants.sh
# Lancement manuel (dev, sans TLS) :
~/.venv-server/bin/uvicorn phototheque.app:app --host 0.0.0.0 --port 8787

# Déploiement détaillé, dépannage, retour arrière : docs/DEPLOIEMENT.md
```

## Historique retiré
Le trieur C++ d'origine (`main.cpp`, `CMakeLists.txt`), ses sous-modules
(`modules/CLI11`, `modules/fmt`) et les lanceurs de bureau qui l'appelaient ont
été supprimés le 2026-09-17 : le trieur Python les remplace. L'historique git
les conserve — inutile de les recréer.

## Workflow
Skills « superpowers » : brainstorming → spec → plan → TDD. Attribution des
commits : voir les consignes de session.
