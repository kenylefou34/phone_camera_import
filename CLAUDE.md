# CLAUDE.md — phone_camera_import

Point de reprise pour les sessions Claude Code. **Documenter/commenter en français**
(le mainteneur débute en Python).

## Le projet
Système d'import de médias : téléphone → NUC → bibliothèque rangée par type et
date (`Photos|Videos/ANNÉE/"MM MOIS"`). Refonte en cours sur la branche `dev`.

Vision : **Phase 1** import (trieur + service + app) ; **Phase 2** consultation web
+ revue visuelle (doublons, floues/rafales, re-datation) ; **Phase 3** visages ;
**Phase 4** génération (livre photo…).

## État actuel (2026-09-24)
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
  **Sa recette est caduque** : le lot 1 bis l'a refondue et élargie, c'est
  celle-là qu'il faut suivre (section REPRISE).
  **Mode d'emploi complet, rejouable depuis zéro : `docs/APPLICATION-ANDROID.md`**
  (outillage sans sudo, compilation, dépôt de l'APK, installation, appairage,
  dépannage). Tests : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest`
  (⚠️ `./gradlew test --tests` échoue : utiliser `testDebugUnitTest --tests`).
  L'APK se dépose sur le NUC par `./deploy/envoyer-apk.sh` et se télécharge
  depuis la page d'admin, derrière le mot de passe.
- ✅ **Lot 1 bis de l'app ÉCRIT** (issue #29) : la synchro est devenue observable
  et pilotable — service de premier plan + `WorkManager` (elle survit à l'écran
  éteint), découpage en **paquets** d'environ 500 Mo chacun validé par son propre
  commit, écran d'avancement complet (n/total, Mo/s, fichier en cours et **sa
  destination**, dossiers suivis), bouton « Interrompre » dans l'app et dans la
  notification, reprise automatique après coupure subie, délais HTTP explicites.
  **144 tests** côté app, 264 côté serveur. Icône et icône de notification
  dédiées. Plan : `docs/superpowers/plans/2026-09-21-app-android-lot1bis.md`.
  **A tourné sur le téléphone du mainteneur le 2026-09-23** : APK installé, QR
  scanné, une sauvegarde réelle menée. C'est cet usage qui a produit les sept
  retours dont est né le lot 2. Sa **recette formelle**, elle, n'a jamais été
  déroulée — voir la section REPRISE.
- ✅ **APK téléchargeable depuis la page d'admin** : `./deploy/envoyer-apk.sh`
  le dépose sur le NUC (empreinte recalculée à l'arrivée, mise en place atomique),
  route `/apk` derrière le mot de passe. Mode d'emploi complet et rejouable depuis
  zéro : **`docs/APPLICATION-ANDROID.md`**.
- ✅ **Lot 2 de l'app ÉCRIT** (conception `docs/superpowers/specs/2026-09-23-app-android-lot2-design.md`,
  plan `docs/superpowers/plans/2026-09-23-app-android-lot2.md`) : choix des
  dossiers par arborescence (repli des chaînes sans média à enfant unique,
  coche à trois états + case à moitié pleine, aperçu à la demande, filet des
  dossiers entrés par récursivité), fenêtre de dates pilotée depuis le
  téléphone (ordre de reprise à usage unique, comptes avant/après la fenêtre
  tenus séparés), synchronisation automatique (`PeriodicWorkRequest` 6 h,
  WiFi non facturé + en charge, `VerrouSynchro` contre une synchro manuelle
  simultanée), désappairage depuis le téléphone (effacement local
  inconditionnel, route serveur `POST /sync/desappairer`, horizon de synchro
  rendu monotone côté application — voir `docs/CONTRAT-APP.md` §4.5 et §5).
  Trois nouveaux écrans (Dossiers, Sauvegarde, Appareil), atteints depuis
  l'accueil par « Réglages » — mode d'emploi et recette de validation :
  `docs/APPLICATION-ANDROID.md` §8-§9. **240 tests** côté app (144 au lot
  1 bis), **301** côté serveur (264 au lot 1 bis).
  **Écrit et relu, jamais exécuté sur un appareil** — voir la section REPRISE.
- ✅ **Relecture finale du lot 2 (24/09)** : la première à regarder les
  **interactions** entre les douze tâches, chacune relue isolément jusque-là.
  Trois défauts critiques, tous trouvés là et nulle part ailleurs.
  1. La borne basse de la fenêtre de dates **faisait sauter l'horizon
     par-dessus des médias jamais envoyés** — des photos perdues en silence,
     déclenché par un geste banal : *remonter* sa date de début. L'horizon
     d'un dossier amputé par le bas est désormais **gelé** (`Orchestrateur`),
     comme l'est celui d'un dossier en échec.
  2. Cocher l'automatique **grisait « Sauvegarder maintenant » pour toujours**
     et affichait une attente permanente : un `PeriodicWorkRequest` reste
     `ENQUEUED` entre deux passes, il n'est jamais « terminé ». La décision
     est extraite en `EtatTravail.combiner`, pure et testée.
  3. « Interrompre » **détruisait la chaîne périodique** (`cancelUniqueWork`
     ne suspend rien) : plus rien n'était planifié, l'interrupteur restait
     affiché actif. Il reprogramme maintenant, avec six heures de délai pour
     ne pas relancer aussitôt ce qu'on vient d'arrêter.
  Plus : zéro dossier coché ne compte plus comme une réussite (et se voit sur
  l'accueil), « Ne pas sauvegarder » sur un dossier à moitié coché décoche
  enfin sa descendance, **remonter** la date de début ne déclenche plus de
  reprise complète, et trois commentaires faux corrigés. Rapport détaillé
  (non versionné, local à cette machine) :
  `.superpowers/sdd/2026-09-23-app-android-lot2/correction-finale-report.md`.
- Déploiement : `./deploy/install.sh` — voir `docs/DEPLOIEMENT.md`.
- Spécs : `docs/superpowers/specs/` — plans : `docs/superpowers/plans/`.

## ⚠️ REPRISE — première chose à faire

**La recette manuelle sur un vrai téléphone.** Le lot 1 bis a bien tourné une
fois, le 23/09 — installation, appairage, une sauvegarde réelle — et ce sont
les manques constatés ce jour-là qui ont produit le lot 2. Mais **aucune
recette formelle n'a jamais été déroulée**, et **le lot 2 n'a jamais été
exécuté du tout** : il a été écrit, relu tâche par tâche par des agents neufs,
et corrigé, rien de plus. Le lot 2 s'appuie entièrement sur les mécanismes du
lot 1 bis
(service de premier plan, `WorkManager`, paquets) : les éprouver séparément
n'a plus grand sens. La recette à suivre est désormais celle du lot 2 —
**`docs/APPLICATION-ANDROID.md` §9** — qui exerce les deux à la fois.

```bash
cd ~/dev/phone_camera_import && ./deploy/envoyer-apk.sh
# puis sur le telephone : page d'admin -> « Telecharger l'application »
```

**Pourquoi cette recette pèse lourd :** il n'existe dans ce projet **aucun test
d'instrumentation Android**. `WorkManager`, le service de premier plan, les
notifications, le `BroadcastReceiver`, tout Compose et `VerrouSynchro` ne sont
couverts par **rien** d'automatique. Les 240 tests côté app ne disent rien de
ces chemins-là ; les relectures les ont jugés par la lecture, pas par
l'exécution.

La recette (`docs/APPLICATION-ANDROID.md` §9) fait **17 étapes** et chacune
existe pour une raison précise — la suivre telle quelle plutôt que
d'improviser. Si c'est la toute première fois que l'application tourne sur un
appareil, la recette d'origine du lot 1 bis (tâche 10 de
`docs/superpowers/plans/2026-09-21-app-android-lot1bis.md`, 18 étapes) reste
la référence la plus détaillée pour ce que celle du lot 2 ne redemande pas
explicitement : le contenu exact de la notification, la reprise après une
coupure subie, le bouton d'arrêt de la notification elle-même.

**Deux limites restent ASSUMÉES** (issue #33, héritées du lot 1 bis), à ne pas
prendre pour des régressions : interrompre pendant l'envoi d'une grosse vidéo
n'arrête pas le téléversement en cours, et l'écran reste figé pendant ce
temps.

**Ce qu'aucun test ne peut trancher, par ordre d'importance :** qu'un arrêt
demandé affiche le compte réel et non trois zéros ; qu'une permission retirée
donne « Nouvelle tentative programmée » et jamais « En attente d'un réseau » ;
qu'une révocation suivie d'un réappairage ne laisse pas revenir le bandeau
« révoqué » ; que le bouton de la notification arrête sans rouvrir l'app ;
**(lot 2)** qu'une synchro manuelle lancée pendant que l'automatique tourne
n'affiche qu'un seul avancement et que « Interrompre » arrête la bonne —
`VerrouSynchro` n'est exercé par aucun test ; **(lot 2)** qu'un réappairage
reprogramme RÉELLEMENT l'automatique (`WorkManager`, pas seulement
l'interrupteur affiché coché) ; **(lot 2)** que « dernière sauvegarde »
disparaît bien de l'accueil après un réappairage plutôt que d'afficher une
ancienne réussite qui ne dit plus rien du nouveau serveur.

**Après la recette** : les issues #30 (journal serveur + purge des sessions
abandonnées) et #31 (galerie).

## Feuille de route (issues GitHub)
Prochaine étape : **la recette manuelle sur un téléphone** (voir REPRISE) —
le lot 2 attend sa première exécution réelle, et le lot 1 bis sa première
recette formelle. **#29** lot 1 bis (fait, à éprouver), **#12** l'application
elle-même (reste ouverte pour la même raison), puis **#30** journal serveur + purge des sessions abandonnées,
**#31** galerie de consultation (phase 2).

**#16 est CORRIGÉE** (23/09) : le serveur ne détruit plus les médias qu'il n'a
pas su ranger. Ils partent en quarantaine sous `INCOMING_DIR/_echecs/<chemin
envoyé>`, visibles dans un bloc « Médias non rangés » de la page d'admin, et
n'en sortent que par un bouton de purge **manuel** — aucune purge automatique,
qui réintroduirait le défaut avec un délai. La boucle est bornée : un même
contenu au même chemin n'occupe qu'une place, deux contenus différents sont
tous deux conservés. Le gel d'horizon côté application **reste indispensable**
(un média en quarantaine n'est pas dans la bibliothèque) ; `docs/CONTRAT-APP.md`
§4.4 l'explique. *(#32, ouverte le 21/09, en était un doublon ; fermée le
23/09.)*
**#33** porte les deux limites reportées au lot 2 — interruption non immédiate
et écran figé pendant l'envoi d'un gros fichier — avec l'approche technique
retenue en commentaire. **#34** les constats mineurs différés du lot 1 bis. Améliorations/Phase 2 tracées en issues #2 à #10 et #14 à #27
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

**PR #13 (`dev` → `main`) a été fusionnée** : les issues qui portaient un
`closes #N` se sont fermées toutes seules (#2, #3, #10, #14, #15, #19, #21).
#12 reste ouverte, l'application n'ayant jamais été éprouvée sur un appareil.

**Pas de nouvelle PR avant la recette** : tout le lot 1 bis reste sur `dev`
tant que rien n'est validé sur un vrai téléphone. C'est tout l'intérêt de
l'avoir gardé là.

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
- **⚠️ Le lien WiFi du NUC BAT (2026-09-23).** Mesuré sur 40 s :
  **~20 s joignable, ~35 s injoignable, en boucle.**
  ```
  13:25:15 ouvert   13:25:33 ferme   13:25:46 ferme   13:26:09 ouvert
  13:25:21 ouvert   13:25:39 ferme   13:25:52 ferme
  ```
  La machine est allumée et **n'a pas redémarré** (`uptime` = 2 j 4 h), mDNS
  résout correctement `IZQUIERDO-NUC.local` → `192.168.1.21` : ce n'est ni un
  problème d'adresse, ni un service tombé. **C'est le lien radio.**
  Ne pas confondre avec deux symptômes voisins déjà vus : le `?` réseau du
  21/09 (`CONNECTED_SITE`, LAN parfait) et une réattribution d'adresse DHCP.
  Le test qui tranche — sonder plusieurs fois, pas une :
  `for i in $(seq 5); do timeout 2 bash -c "cat </dev/null >/dev/tcp/192.168.1.21/22" && echo ouvert || echo ferme; sleep 4; done`
  Alterné = le lien bat. Toujours fermé = autre chose.
  **La correction est physique : brancher un câble ethernet.** `eno1` n'a
  jamais eu de câble, le WiFi est l'unique chemin, et la dégradation est
  documentée depuis le 19/09 (3 bascules en 16 jours → 6 le 19/09 → 11 le
  20/09 → bloqué le 21/09 → battement le 23/09). Tant que ça dure, **une
  synchro de plusieurs Go et la recette sont hors de portée**.
- **⚠️ `getent hosts IZQUIERDO-NUC.local` n'est PAS fiable ici.** Le 23/09,
  dix appels d'affilée ont échoué pendant qu'`avahi-resolve` répondait sans
  broncher. La cause est dans `/etc/nsswitch.conf` :
  `mdns4_minimal [NOTFOUND=return]` n'interroge que l'IPv4 et **coupe la
  chaîne** dès qu'elle manque — or le NUC annonçait alors son IPv6 sans son
  IPv4. Utiliser :
  `avahi-resolve -4 -n IZQUIERDO-NUC.local`
  Le `-4` n'est pas cosmétique : sans lui, avahi rend l'IPv6 en premier.
- **L'adresse du NUC change** : `.21` le 21/09, `.31` le 23/09 après
  redémarrage. Ne jamais l'écrire en dur. **Les scripts la cherchent** :
  `adresse_nuc()` dans `deploy/lib.sh` résout par `avahi-resolve` puis
  `getent`, **sonde** l'adresse obtenue (résoudre ne prouve pas que la machine
  répond — le 23/09, `.21` répondait au ping sans que rien n'y écoute), refait
  la résolution **à chaque essai**, et retombe sur `NUC_REPLI` en dernier
  recours. Surcharges : `NUC=user@ip`, `NUC_HOTE`, `NUC_REPLI`.
- **`eno1` (ethernet du NUC) n'a aucun câble** (`cat /sys/class/net/eno1/carrier`
  = 0) : le WiFi est l'unique chemin vers le serveur photo. Un câble le rendrait
  insensible aux aléas radio — action physique, à la main du mainteneur.

**Pièges de l'application Android**
- **Le manifeste qui compte est le manifeste FUSIONNÉ**, pas la source. Le lot
  1 bis a failli livrer un plantage garanti sur tout appareil : `WorkManager`
  déclare son propre service de premier plan **sans** `foregroundServiceType`,
  alors que le code lui passe `DATA_SYNC` — et depuis Android 10 la plate-forme
  refuse un type qui n'est pas un sous-ensemble de celui du manifeste, par une
  exception que `WorkManager` n'attrape pas. Invisible à la compilation et aux
  tests. Le contrôle :
  `grep -c foregroundServiceType android/app/build/intermediates/merged_manifests/debug/processDebugManifest/AndroidManifest.xml`
- **Déclarer une permission ne suffit pas** depuis Android 13 :
  `POST_NOTIFICATIONS` doit être **demandée à l'exécution**, sinon la
  notification n'apparaît jamais — et avec elle l'avancement écran éteint et le
  bouton d'arrêt.
- **La zone sûre d'une icône adaptative** est le cercle de rayon 33 sur un
  canevas de 108 : les lanceurs rognent en cercle, en carré arrondi ou en
  goutte, et tout ce qui dépasse disparaît sur certains téléphones.
- **`ExistingWorkPolicy.KEEP`** empêche deux synchros en parallèle, mais rend
  aussi le bouton muet tant qu'un travail est en attente : l'écran doit dériver
  son état de `WorkManager` (`getWorkInfosForUniqueWorkFlow`) et non d'un
  drapeau posé à la main, sinon il reste « en cours » pour toujours.
- **`ExistingWorkPolicy.KEEP` (et `ExistingPeriodicWorkPolicy.KEEP`) ne
  protègent chacune qu'À L'INTÉRIEUR de leur propre nom unique** (lot 2) : la
  file manuelle (« synchro ») et la file automatique (« synchro-auto »)
  peuvent très bien démarrer en même temps, alors que `TravailSynchro` garde
  son avancement, sa dernière issue et son drapeau d'arrêt dans le
  `companion object` de la classe — partagés par TOUTE exécution, quelle que
  soit la file qui l'a déclenchée. D'où `VerrouSynchro` (exclusion mutuelle
  par `AtomicBoolean.compareAndSet`, sans préemption), qu'**aucun test
  n'exerce** — seule la recette manuelle (`docs/APPLICATION-ANDROID.md` §9,
  étape 12) le fait.
- **`ExistingPeriodicWorkPolicy.KEEP` ne reprogramme pas** : reprogrammer à
  chaque ouverture d'écran remettrait le compteur des 6 h à zéro, et la passe
  automatique n'aurait jamais lieu sur un téléphone qu'on ouvre souvent. Un
  réappairage, lui, doit reprogrammer pour de vrai si l'automatique était
  coché — un désappairage l'avait déprogrammé sans toucher au réglage
  affiché.
- **Un `PeriodicWorkRequest` n'atteint JAMAIS d'état terminal** (relecture
  finale du lot 2) : entre deux passes il reste `ENQUEUED`, donc
  `!state.isFinished` y est vrai en permanence. Un écran qui en déduit « un
  travail attend » affiche une attente éternelle et grise son bouton pour
  toujours, dès la seconde où l'utilisateur coche l'automatique. La file
  périodique ne doit contribuer qu'à « en cours » ; l'attente et la nouvelle
  tentative ne se lisent que sur la file **manuelle**.
- **`cancelUniqueWork` sur un travail périodique ne suspend pas la passe : il
  DÉTRUIT la chaîne.** Plus rien n'est planifié, et le réglage reste affiché
  actif. Il faut replanifier derrière — mais avec un **délai initial**, car
  un `PeriodicWorkRequest` neuf démarre dès que ses contraintes sont
  satisfaites, sans attendre sa première période : sans ce délai, le bouton
  « Interrompre » relancerait aussitôt ce qu'il vient d'arrêter (téléphone en
  charge sur le WiFi de la maison = contraintes satisfaites, c'est-à-dire
  exactement le cas où l'on appuie).
- **Les bornes de la fenêtre de dates sont asymétriques par construction**
  (UTC+14 pour le début, UTC-12 + 1 jour pour la fin) : le téléphone ignore le
  fuseau dans lequel une photo a été prise, et le principe retenu est
  « reproposer plutôt que sauter ». Réutiliser la borne basse pour construire
  la borne haute arrêterait la fenêtre à midi UTC le jour choisi — ~14 h à
  Paris — et ferait disparaître en silence toutes les photos de l'après-midi
  et de la soirée du dernier jour.

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
- **Corrigé par le lot 2** : `Devices.revoke()` supprimait la ligne `devices`
  mais pas ses horizons (pas de clé étrangère, `PRAGMA foreign_keys` jamais
  activé — SQLite le laisse inactif par défaut). Elle exécute désormais aussi
  `DELETE FROM horizons WHERE appareil=?`. Et le téléphone **peut** maintenant
  se retirer lui-même par `POST /sync/desappairer` (`require_device`, pas
  `require_admin`) — voir `docs/CONTRAT-APP.md` §4.5.
- **Le serveur pose `horizon_initial = date.today()` à CHAQUE appairage**
  (`Devices.pair()`, `phototheque/devices.py:94`), même quand personne ne
  touche au formulaire de `/pair`, et même pour un réappairage du même
  téléphone. Un réappairage ne relit donc PAS l'historique complet : il
  faut reposer une date de début côté application pour reprendre les médias
  plus anciens que le jour du réappairage — voir `docs/CONTRAT-APP.md` §4.1.

**Tests**
- Simuler une machine d'origine : `TestClient(app, client=("192.168.1.50", 1))`.
- Les tests d'app rechargent `config` **puis** `app` (`importlib.reload`) après
  avoir posé les variables d'environnement — sinon les chemins restent ceux de
  l'import initial.
- Un test qui passe du premier coup ne prouve rien. Systématiquement le valider
  **par mutation** : casser volontairement le code et vérifier que c'est bien ce
  test-là qui tombe. Plusieurs faux verts ont été attrapés ainsi le 18/09
  (script absent → code 127, propriétés déjà vraies avant correctif).
- **Un test qui construit ses données avec la fonction qu'il teste est
  auto-cohérent et vide de sens.** Rencontré à la tâche 8 du lot 2 (fenêtre de
  dates) : un test qui fabriquait son instant attendu avec la même fonction
  d'ancrage que le code testé (`jourVersSecondes`, réutilisée pour les deux
  bornes) ne pouvait pas voir que la borne haute, calculée comme la borne
  basse + 24 h, arrêtait en réalité la fenêtre à ~14 h à Paris et perdait en
  silence toutes les photos de l'après-midi du dernier jour. Le correctif :
  construire les instants attendus **hors de** la fonction testée, sur des
  fuseaux réels (Paris, Tokyo, Los Angeles).

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
- **`gh issue view` est cassé sur ce dépôt**, pour la même raison que
  `gh pr edit` : il interroge l'API « Projects classic », supprimée par GitHub.
  Passer par `gh api "repos/$REPO/issues/N" -q '.title, .body'`. `gh issue
  create` et `gh issue list`, eux, fonctionnent.
- **Ne jamais passer un message de commit par `git commit -m "..."`** s'il
  contient des accents graves : bash les prend pour des substitutions de
  commande et efface des mots, laissant des phrases à trous. C'est arrivé le
  21/09 sur `836e447`. Toujours un heredoc à délimiteur quoté :
  `git commit -F - <<'FIN'`.
- **`git commit --amend` est sûr… sauf quand un agent travaille dans le dépôt** :
  il réécrirait SON commit s'il en produit un entre-temps. Attendre.
- **`gh` ne ferme une issue qu'à la fusion dans la branche par défaut** : les
  `closes #N` de `dev` ne prendront effet qu'à la fusion de la PR #13.
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
#   (DEPUIS UN TELEPHONE : utiliser l'IP, pas le nom .local — les navigateurs
#    Android ne resolvent pas le mDNS. `avahi-resolve -4 -n IZQUIERDO-NUC.local`
#    donne l'IP du moment. L'application, elle, passe par NsdManager et n'a pas
#    ce probleme.)
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
