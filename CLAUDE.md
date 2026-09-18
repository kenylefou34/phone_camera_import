# CLAUDE.md — phone_camera_import

Point de reprise pour les sessions Claude Code. **Documenter/commenter en français**
(le mainteneur débute en Python).

## Le projet
Système d'import de médias : téléphone → NUC → bibliothèque rangée par type et
date (`Photos|Videos/ANNÉE/"MM MOIS"`). Refonte en cours sur la branche `dev`.

Vision : **Phase 1** import (trieur + service + app) ; **Phase 2** consultation web
+ revue visuelle (doublons, floues/rafales, re-datation) ; **Phase 3** visages ;
**Phase 4** génération (livre photo…).

## État actuel (2026-09-18)
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
  **233 tests**.
- ✅ **Contrat serveur de l'app écrit** (issue #15) : `docs/CONTRAT-APP.md`,
  exemples **capturés sur un échange réel**. À lire avant d'écrire l'app (#12) ;
  la section 6 de la spec y renvoie.
- Déploiement : `./deploy/install.sh` — voir `docs/DEPLOIEMENT.md`.
- Spécs : `docs/superpowers/specs/` — plans : `docs/superpowers/plans/`.

## ⚠️ REPRISE — état au 2026-09-18 (fin de session)

**Tout est déployé et vérifié sur le NUC** (`5ad55b5` au moment d'écrire ; le
service a été relancé et la surface contrôlée : `/`, `/pair`, `/devices` et
`/status` en 401, `/docs`, `/redoc` et `/openapi.json` en 404).

Le mainteneur a choisi ses identifiants avec `./deploy/identifiants.sh` —
l'identifiant n'est plus `admin`. Si besoin : `rm ~/.config/phototheque/utilisateur`
le ramène à `admin`.

**Sécurité du réseau** (voir la mémoire `projet-nuc-exposition-reseau`) : le
serveur photo n'est **pas** joignable depuis Internet. Plex avait ouvert tout
seul un port sur la box via UPnP ; l'accès distant a été coupé le 18/09 et il
ne reste aucune redirection. L'UPnP de la box reste activé — un programme peut
donc encore s'ouvrir un accès sans prévenir ; à couper un jour, en sachant que
ça peut gêner console de jeu et visio.

**Prochaine étape** : sous-projet 3, l'application Android (issue #12). Le
contrat qu'elle doit implémenter est écrit : **`docs/CONTRAT-APP.md`** (#15,
fait le 18/09). Lire aussi #22 : l'app devra hacher chaque fichier avant de
savoir s'il est utile, ce qui coûte cher sur un téléphone. Voir aussi le commentaire du 18/09 sur #12 : prévoir un lien de
téléchargement de l'APK sur la page du serveur.

**Fait le 17/09** : rattrapage des signatures sur le NUC (44 669 médias en
16 min) ; renommage `mediaserve` → `phototheque` ; retrait du trieur C++ ;
refonte des pages web ; README et `DEPLOIEMENT.md` réécrits pas à pas.

## Feuille de route (issues GitHub)
Prochaine étape : **sous-projet 3 = app Android** (issue #12 : scan QR, scan des
dossiers, client d'upload) — commencer par #15, qui fige le contrat qu'elle
codera en dur. Améliorations/Phase 2 tracées en issues #2 à #10 et #14 à #22
(`gh issue list`). Notamment : #4 doublons existants, #5 floues/rafales,
#6 re-datation, #7 sauvegarde Famille.

Le travail de #2, #3, #10, #14, #15, #19 et #21 est **fait** (#8, #9 et #11 sont fermées), mais
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
- Pas de `curl` sur le NUC ; `sudo` exige un vrai terminal (le canal `!` n'a pas
  de TTY) ; PEP 668 impose le venv.

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
