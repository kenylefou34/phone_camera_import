# CLAUDE.md — phone_camera_import

Point de reprise pour les sessions Claude Code. **Documenter/commenter en français**
(le mainteneur débute en Python).

## Le projet
Système d'import de médias : téléphone → NUC → bibliothèque rangée par type et
date (`Photos|Videos/ANNÉE/"MM MOIS"`). Refonte en cours sur la branche `dev`.

Vision : **Phase 1** import (trieur + service + app) ; **Phase 2** consultation web
+ revue visuelle (doublons, floues/rafales, re-datation) ; **Phase 3** visages ;
**Phase 4** génération (livre photo…).

## État actuel (2026-09-25)
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
  retours dont est né le lot 2. Sa **recette formelle** à elle seule n'a
  jamais été déroulée à part : c'est celle du lot 2, qui exerce les mêmes
  mécanismes (service de premier plan, `WorkManager`, paquets), qui est en
  cours depuis le 24/09 — voir la section REPRISE.
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
  **Exécuté sur un vrai téléphone depuis le 24/09** (HONOR 90 Lite),
  partiellement validé — étapes 1 à 8, 9 bis, 10, 13 à 17 faites, étapes 11 et
  12 restantes — voir la section REPRISE.
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
  reprise complète, et trois commentaires faux corrigés. Le rapport détaillé
  (non versionné, sous `.superpowers/`) a été supprimé le 25/09 à la demande du
  mainteneur, une fois la recette rejouée ; les constats différés vivent dans
  #41, l'historique des correctifs dans les messages de commit.
- ✅ **Recette du lot 2 commencée sur un vrai téléphone (24/09)** : HONOR 90
  Lite (Android 15), NUC alors en `192.168.1.31`. Le téléphone ne portait
  encore que l'APK du lot 1 bis (23/09) : premier APK du lot 2 installé par
  `adb install -r` en débogage sans fil (même clé de signature, appairage
  conservé), serveur du NUC mis à jour jusqu'à `066a062`. Étapes **1 à 8**,
  **9 bis** (reprise partielle refusée tant que les travaux ne sont pas
  finis — variante testée avec un début au 20/09), **10**, **13 à 17**
  validées (`docs/APPLICATION-ANDROID.md` §9). Restent l'étape 11 (nuit en
  charge, lancée le soir du 24/09, résultat à relever) et l'étape 12
  (croisement manuel/automatique), constatée partielle — détail en section
  REPRISE.
- ✅ **Cinq constats de cette recette corrigés, plus #36 et #38** — tous sur
  `dev` (branche `worktree-constats-recette-lot2` fusionnée le 24/09),
  **réinstallés et rejoués le 25/09** : C1 (verrou muet : une synchro arrêtée
  pendant un appel bloquant gardait `VerrouSynchro`, tout lancement suivant
  sortait en « réussite » muette — relance sans plafond,
  `Reprise.apresRefusDuVerrou`, `7792efb`), C2 (aucun journal côté app,
  `d28e221`), C3 (écran « Cet appareil » rouvert après réappairage, avec un
  vrai désappairage accidentel le 24/09 — `Navigation.demandeApres`,
  `c4bb1b3`), C4 (QR bloqué en paysage — surcharge du manifeste de la
  bibliothèque de scan, `c4bb1b3`), C5 (champ date de `/pair` retiré avec
  `POST /pair`, `a6d5d48`), #36 (l'accueil annonce les dossiers gelés), #38
  (décocher annonce les sous-dossiers emportés).
- ✅ **Journal serveur + sessions abandonnées ÉCRIT** (issue #30, et #27
  réglée) : base à part `~/phototheque_journal.db` (synchros, mouvements par
  fichier, événements), purge des sessions oubliées depuis plus de 24 h
  (démarrage + après chaque commit, quarantaine `_echecs` jamais touchée),
  `POST /sync/abandon` (bouton « Interrompre »), quatre pages d'historique
  (`/historique`, `/historique/<id>`, `/historique/recherche`,
  `/evenements`), chaque commit du téléphone porte désormais son identifiant
  de synchro et son bilan applicatif. Le trieur en ligne de commande affiche
  enfin le compte des fichiers ignorés (issue #27). Documenté dans
  `docs/CONTRAT-APP.md` et `docs/DEPLOIEMENT.md` — les nouveaux exemples y
  sont **illustratifs**, restent à capturer sur un échange réel à la
  prochaine recette. **Relecture finale de la branche (24/09)** : la purge
  laisse désormais un mouvement nominatif par fichier supprimé, un commit
  sur une session purgée ou abandonnée est refusé (`410`, aucun horizon
  écrit), le journal est transactionnel et ne ralentit plus un tri quand sa
  base est verrouillée, les deux purges (sessions / quarantaine) ne se
  confondent plus sur `/evenements`. **383 tests** côté serveur (299 en
  début de session), **262** côté app (240 en début de session).
- ✅ **`dev` réinstallé et recette rejouée (25/09)** : NUC mis à jour à
  `d3b7789` (`incoming/` vide avant le premier démarrage qui purge ; service
  redémarré à 09:09:14, journal `~/phototheque_journal.db` créé), APK de `dev`
  installé sur le HONOR 90 Lite **et** déposé sur le NUC (la page d'admin
  distribuait encore celui du 24/09 07:55, antérieur à C1-C5). Validés :
  **C3 + C4** (réappairage en portrait, arrivée sur l'accueil), **C2** (départ
  et issue de chaque synchro dans `logcat`, une fois le filtre HONOR levé),
  **C1** (croisement réel de deux exécutions de la file automatique au
  branchement : la seconde refusée par `VerrouSynchro`, repartie seule 80 s
  plus tard), **#30** (une ligne d'historique par synchro avec ses
  destinations, événements tracés, vrai `POST /sync/abandon` au bouton
  « Interrompre »), **étape 12** (l'accueil cache « Sauvegarder maintenant »
  pendant une passe automatique : un seul avancement ; « Interrompre »
  reprogramme l'automatique avec 6 h de délai, contrôlé dans `WorkManager`),
  réappairage qui **reprogramme réellement** l'automatique. **Les exemples
  « illustratifs » de `docs/CONTRAT-APP.md` sont remplacés par des captures
  réelles.** Reste l'**étape 11** (nuit), ratée le 24/09 — voir REPRISE.
  Trouvé en route : le gestionnaire d'énergie HONOR, le filtre de journaux
  HONOR, le piège « `/pair` réaffiche le même QR », et **#42**.
- ✅ **Galerie de consultation, partie serveur, ÉCRITE — PAS ENCORE
  DÉPLOYÉE** (issue #31, phase 2, branche `galerie-serveur`, plan
  `docs/superpowers/plans/2026-09-25-galerie-consultation-serveur.md`, neuf
  tâches) : classement d'un chemin en type/origine/date, index en mémoire
  avec filtres et compteurs année/mois/jour, vues paginées, vignettes WebP
  (400 px, EXIF ou `ffmpeg`) fabriquées par un service de fond **séparé**
  (`phototheque-recensement`, `nice` 19, E/S au repos, reprenable, se tait
  pendant une synchro téléphone), routes de lecture seule ouvertes au mot de
  passe admin OU au jeton d'un appareil (`require_lecteur`, prépare l'onglet
  `WebView` de l'app). **`/` est devenue la galerie, l'administration est
  passée à `/admin`.** 508 tests dans la suite pytest (383 avant ce lot).
  **Jamais installée sur le NUC** : reste l'étape 7 de la tâche 9
  (`./deploy/install.sh`, avec le mainteneur, sudo — sauvegarder
  `~/mediasort_catalog.db` avant) — voir `docs/DEPLOIEMENT.md`, « La galerie
  et son recensement ».
- Déploiement : `./deploy/install.sh` — voir `docs/DEPLOIEMENT.md`.
- Spécs : `docs/superpowers/specs/` — plans : `docs/superpowers/plans/`.

## ⚠️ REPRISE — première chose à faire

**Relever l'étape 11 de la recette du lot 2**, relancée le soir du 25/09 :
une nuit en charge sur le WiFi, application **non ouverte**, et une passe
`synchro auto` qui doit avoir eu lieu sans intervention. C'est la seule étape
encore ouverte (`docs/APPLICATION-ANDROID.md` §9) ; tout le reste a été
réinstallé et validé le 25/09 (voir l'État actuel).

1. **Vérifier d'abord côté serveur**, sans le téléphone :
   ```bash
   ssh izquierdo@$(avahi-resolve -4 -n IZQUIERDO-NUC.local | cut -f2) \
     'journalctl -u phototheque --since "yesterday 20:00" --no-pager | grep sync/'
   ```
   Des `POST /sync/plan` et `/sync/commit` dans la nuit = réussite (et une
   ligne nocturne sur `/historique`). Rien du tout = échec : passer au 2.
2. **En cas d'échec**, dans cet ordre (débogage sans fil, adresse et port
   donnés par le mainteneur) :
   - `adb shell dumpsys activity exit-info fr.izquierdo.phototheque` — une
     ligne `iAwareR[SmartClean]` pendant la nuit = le gestionnaire d'énergie
     HONOR a encore tué l'application : les deux réglages de
     `docs/APPLICATION-ANDROID.md` §11 (« La sauvegarde automatique ne tourne
     jamais la nuit ») n'ont pas pris, ou ne suffisent pas ;
   - `adb shell dumpsys deviceidle whitelist | grep izquierdo` (doit
     répondre si « Ne pas optimiser » a pris) ;
   - la base `WorkManager` (`period_count` de `synchro-auto`) ;
   - `adb shell setprop log.tag.Phototheque I` **avant** tout
     `logcat` : ce téléphone jette les journaux des applications tierces
     (`persist.log.tag=S`), réglage perdu à chaque redémarrage.
3. **Si l'étape 11 passe** : fermer à la main **#12** et **#29**, puis ouvrir
   la PR `dev` → `main` (elle fermera #36 et #38).
4. Puis **#31** (galerie de consultation, phase 2). **Neuf tâches ÉCRITES le
   25/09** sur la branche `galerie-serveur` (plan
   `docs/superpowers/plans/2026-09-25-galerie-consultation-serveur.md` ;
   l'onglet `WebView` de l'app fera un plan à part). Reste seulement l'étape
   7 de la tâche 9 : **installer et valider sur le NUC, avec le mainteneur**
   (sudo, sauvegarder `~/mediasort_catalog.db` avant tout) — voir
   `docs/DEPLOIEMENT.md`, « La galerie et son recensement ». **#43** (ouverte
   le 25/09) : l'app doit reprendre le thème de l'admin, la galerie aussi.

**Pourquoi l'étape 11 a échoué le 24/09 — deux causes, chacune suffisante :**
l'appareil avait été révoqué depuis l'admin à 13:38 (le téléphone portait un
jeton mort, `401` à 13:39, plus aucune requête ensuite), et le gestionnaire
d'énergie HONOR (`iAwareR[SmartClean]`) a tué l'application à 18:43 — la
passe périodique n'a jamais démarré (`period_count = 0`) alors que le
téléphone est resté branché jusqu'à 07:06. Le mécanisme lui-même n'est pas en
cause : une passe automatique a été vue aller au bout sur secteur le 25/09.

**Ce que la recette n'a pas pu trancher (aucun scénario atteignable) :**
qu'« Interrompre » efface une nouvelle tentative programmée de la file
**manuelle** — pendant une passe automatique, l'accueil cache « Sauvegarder
maintenant », si bien qu'une manuelle ne peut plus être refusée par le verrou
depuis l'écran ; et qu'un arrêt demandé affiche le compte réel et non trois
zéros (l'arrêt du 25/09 est tombé avant le premier envoi : le compte réel
*était* zéro).

**Toujours vrai :** il n'existe dans ce projet **aucun test
d'instrumentation Android**. `WorkManager`, le service de premier plan, les
notifications, le `BroadcastReceiver`, tout Compose et `VerrouSynchro` ne
sont couverts par rien d'automatique : seule la recette les exerce.

**Deux limites restent ASSUMÉES** (issue #33) : interrompre pendant l'envoi
d'une grosse vidéo n'arrête pas le téléversement en cours, et l'écran reste
figé pendant ce temps.

## Feuille de route (issues GitHub)
Prochaine étape : **relever l'étape 11** (voir REPRISE), puis **#31** galerie
de consultation (phase 2). **#29** (lot 1 bis) et **#12** (l'application
elle-même) restent ouvertes jusqu'à ce que l'étape 11 passe. **#30** (journal
serveur + purge des sessions abandonnées) et **#27** (compteur d'ignorés du
trieur en ligne de commande) ont été **validées sur le NUC et fermées à la
main le 25/09**. **#42**, ouverte le 25/09 : un arrêt subi s'écrit
« terminée » dans le journal Android (faible, contournement documenté).

**Quatre issues ouvertes le 24/09 par la relecture finale du lot 2.** **#36**
(l'accueil annonce désormais les dossiers gelés par la date de début) et
**#38** (décocher largement annonce désormais les sous-dossiers emportés)
sont **CORRIGÉES sur `dev`** ; leurs commits portent `Closes`, elles se
fermeront seules à la fusion dans `main` (`gh` ne ferme qu'à la branche par
défaut). Restent ouvertes,
non bloquantes pour la recette : **#37** la ligne de l'arborescence ne livre
qu'une partie de la spec §3.4 (période couverte, noms des sous-dossiers,
indice de nature) ; **#39** interrompre une sauvegarde *manuelle* repousse
aussi la passe automatique de 6 h.

**#40**, ouverte le 24/09 : passer le code du projet à l'anglais en gardant la
documentation en français — non prioritaire, pour plus tard.

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
17/09 — ils n'avaient aucune trace jusqu'au 21/09). **#27, la moitié restante
du constat C2 de ce lot, est CORRIGÉE sur `dev`** : le trieur en ligne
de commande affiche désormais le compte des fichiers ignorés (extension non
gérée) dans son bilan (`mediasort/cli.py`). Le seul qui ait *gagné* en portée
depuis son signalement est le court-circuit temporel sur le nom
d'utilisateur, devenu un secret partiel depuis `identifiants.sh`.

**PR #13 (`dev` → `main`) a été fusionnée** : les issues qui portaient un
`closes #N` se sont fermées toutes seules (#2, #3, #10, #14, #15, #19, #21).
#12 reste ouverte : l'application tourne sur un appareil depuis le 24/09, les
correctifs C1 à C5 y ont été réinstallés et rejoués le 25/09, mais l'étape 11
de la recette (une nuit en charge) reste à relever.

**Pas de nouvelle PR `dev` → `main` avant la fin de la recette (étape 11)** : tout le lot 1 bis et
le lot 2 restent sur `dev` tant que rien n'est validé sur un vrai téléphone.
C'est tout l'intérêt de les avoir gardés là. La branche
`worktree-constats-recette-lot2` (corrections C1 à C5, #30, #27, #36, #38 et
la relecture finale) a été **fusionnée dans `dev` le 24/09** (avance rapide) ;
les constats différés de sa relecture finale sont dans **#41**.

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
- **Le débogage sans fil (`adb`) change d'adresse ET de port à chaque
  activation** (constaté le 24/09 : l'adresse du téléphone est passée de
  `.27` à `.18` dans la même journée). Un premier `adb connect` peut échouer
  si le téléphone dort — réessayer suffit, ce n'est pas une panne.
- **Toujours vérifier la version réellement installée avant une recette** :
  `adb shell dumpsys package fr.izquierdo.phototheque | grep lastUpdateTime`.
  Le 24/09, le téléphone portait encore l'APK du lot 1 bis (23/09) alors que
  la recette du lot 2 était censée démarrer — elle n'avait donc jamais pu
  tourner jusque-là.
- **Pour un APK antérieur à C2 (aucun journal Android)**, l'état réel d'une
  synchro se lit dans la base `WorkManager` plutôt que dans les journaux :
  `adb exec-out run-as fr.izquierdo.phototheque cat no_backup/androidx.work.workdb`
  (+ `-wal`, `-shm`) et `adb shell dumpsys jobscheduler`.
- **Le HONOR 90 Lite jette les journaux de toutes les applications tierces**
  (25/09) : `persist.log.tag=S`. `adb logcat -s Phototheque` reste vide même
  avec un APK postérieur à C2 — ce n'est pas une régression. Lever le filtre
  par `adb shell setprop log.tag.Phototheque I` (sans root, perdu au
  redémarrage du téléphone).
- **Le gestionnaire d'énergie HONOR tue l'application, et avec elle la
  sauvegarde automatique** (`iAwareR[SmartClean]` dans `adb shell dumpsys
  activity exit-info fr.izquierdo.phototheque`). Plus aucun travail planifié
  ne part jusqu'à la prochaine ouverture à la main. Correction côté
  téléphone uniquement : `docs/APPLICATION-ANDROID.md` §11.
- **`/pair` réaffiche LE MÊME QR tant que l'appairage affiché n'a pas servi.**
  Désappairer depuis le téléphone APRÈS avoir chargé `/pair` confirme puis
  supprime cet appairage-là : le QR resté à l'écran est mort, et la première
  sauvegarde répond « révoqué ». Toujours désappairer d'abord, charger
  `/pair` ensuite.
- **`cmd jobscheduler run -f` ne suffit pas à forcer la passe automatique
  sans recharge** : WorkManager l'arrête dans la demi-seconde. Pour une passe
  à la demande, brancher le téléphone puis décocher et recocher
  « Sauvegarder automatiquement » (un travail périodique neuf part dès que
  ses contraintes sont réunies).

**Pièges du serveur**
- **L'adresse `/` du NUC n'est plus l'administration** (issue #31, galerie de
  consultation) : `/` sert désormais la galerie de photos en lecture seule
  (mot de passe admin OU jeton d'un appareil appairé, `require_lecteur`),
  l'administration (appareils, camembert disque, APK, historique, bloc
  « Galerie ») est passée à `/admin`. Un signet ou un raccourci gardé sur
  l'ancienne adresse ouvre la galerie, pas l'admin.
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
  (`Devices.pair()`, `phototheque/devices.py:94`), et plus rien ne le
  règle côté serveur : le champ date de `/pair` a été retiré le 24/09
  (constat C5), la date de début du téléphone primant toujours. Vrai même pour un réappairage du même
  téléphone. Un réappairage ne relit donc PAS l'historique complet : il
  faut reposer une date de début côté application pour reprendre les médias
  plus anciens que le jour du réappairage — voir `docs/CONTRAT-APP.md` §4.1.
- **La quarantaine `_echecs` vit DANS `INCOMING_DIR`** (issue #30) : toute
  purge de ce dossier doit l'écarter, sous peine de réintroduire l'issue #16
  (médias non rangés détruits) avec un simple délai. La purge des sessions
  abandonnées de 24 h l'écarte déjà par construction, sans avoir à la nommer :
  elle ne considère que les dossiers dont le nom a la forme d'un identifiant
  de session (32 hexadécimaux), et `_echecs` n'a pas cette forme.
- **`sync_commit` traite un dossier de session ABSENT comme une session
  VIDE, et fait quand même avancer l'horizon** (voir sa docstring) : la purge
  des sessions abandonnées (24 h) suppose donc qu'une session ne reste jamais
  **sans écriture** plus de 24 h (le critère est la date du fichier le plus
  récent de toute l'arborescence, pas le temps depuis le premier envoi). Vrai
  aujourd'hui, car l'application fait plan/envoi/commit d'une seule traite —
  à reconsidérer si elle se met un jour à garder une session ouverte plus
  longtemps. Filet depuis la relecture finale : le journal retient les
  sessions purgées ou abandonnées (`sessions_retirees`) et un commit sur l'une
  d'elles répond `410` sans toucher aux horizons — contrôlé avant ET après le
  tri. Un journal illisible rend ce contrôle muet (comportement d'avant),
  jamais bloquant.
- **Le premier démarrage d'une version qui purge supprime les sessions de
  plus de 24 h déjà présentes dans `incoming/`** : inventaire AVANT
  `install.sh` (`docs/DEPLOIEMENT.md`, « Au premier démarrage d'une version
  qui purge »). La trace nominative par fichier dit ce qui a disparu, elle ne
  le rend pas.
- **Un `/sync/commit` rejoué pour la même session n'est pas recompté dans le
  journal** (table `commits` de `phototheque/journal.py`) : si la réponse
  HTTP se perd (WiFi instable du NUC) et que le téléphone retente avec le
  même identifiant de session, le bilan cumulé de la synchro n'est pas
  doublé.

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
# puis https://IZQUIERDO-NUC.local:8787/ (galerie, lecture seule) et
#   /admin (administration, identifiant "admin") et /pair (QR)
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
