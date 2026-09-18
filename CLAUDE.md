# CLAUDE.md — phone_camera_import

Point de reprise pour les sessions Claude Code. **Documenter/commenter en français**
(le mainteneur débute en Python).

## Le projet
Système d'import de médias : téléphone → NUC → bibliothèque rangée par type et
date (`Photos|Videos/ANNÉE/"MM MOIS"`). Refonte en cours sur la branche `dev`.

Vision : **Phase 1** import (trieur + service + app) ; **Phase 2** consultation web
+ revue visuelle (doublons, floues/rafales, re-datation) ; **Phase 3** visages ;
**Phase 4** génération (livre photo…).

## État actuel (2026-09-17)
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
  Adresse : `https://IZQUIERDO-NUC.local:8787/`, identifiant `admin`.
  **194 tests**.
- Déploiement : `./deploy/install.sh` — voir `docs/DEPLOIEMENT.md`.
- Spécs : `docs/superpowers/specs/` — plans : `docs/superpowers/plans/`.

## ⚠️ REPRISE — première chose à faire (2026-09-18)

Le lot #3 + #10 + #2 est **écrit, revu et poussé**, mais **toujours pas déployé**.
Vérifié le 18/09 : le NUC tourne `6111a68`, soit **40 commits de retard** (et non
`3de5fcd` comme écrit précédemment). Concrètement `/` répond 200 **sans mot de
passe** et `~/.config/phototheque/` n'existe pas : ni certificat, ni mot de passe.
Le 401 sur `/status` vient de l'ancien jeton d'appareil, pas de la nouvelle
authentification — il ne prouve rien.

**1. Déployer** — à lancer par le mainteneur, dans un vrai terminal (mot de passe
sudo, le canal `!` n'a pas de TTY) :

```bash
cd ~/phone_camera_import && git pull && ./deploy/install.sh
```

Le script **affiche le mot de passe d'administration une seule fois** : le noter.
Puis vérifier, comme le prévoit la tâche 15 du plan :
- `https://IZQUIERDO-NUC.local:8787/` répond (avertissement navigateur au premier
  accès, normal : certificat auto-signé, « Paramètres avancés » puis
  « Continuer », une fois par appareil) ;
- l'empreinte affichée par le script correspond à
  `openssl s_client -connect 127.0.0.1:8787 … | openssl x509 -noout -fingerprint -sha256` ;
- `avahi-browse -tpr _phototheque._tcp` depuis une autre machine ;
- le QR de `/pair` reste scannable malgré les 64 caractères d'empreinte ajoutés ;
- `hostname -I` ne renvoie qu'une adresse (sinon le SAN du certificat pourrait
  viser la mauvaise — constat mineur différé).

**2. Les deux questions en suspens sont tranchées (18/09)** — plus rien à décider :
- **5 issues de suivi ouvertes** : #15 contrat serveur de l'app, #16 nettoyage de
  session qui détruit les fichiers en échec, #17 `_appairage_en_cours` face à
  plusieurs workers, #18 Docker sans certificat ni mot de passe, #19 limitation
  d'essais du mot de passe.
- **Les 2 sauvegardes du NUC sont supprimées.** Vérifié avant : le catalogue
  vivant a ses 44 669 signatures, la sauvegarde n'avait même pas la colonne ;
  la base d'appareils sauvegardée contenait 0 appareil.

**3. Ensuite** : sous-projet 3, l'application Android (issue #12). Tout ce lot
existait pour figer le contrat qu'elle codera en dur — voir la section 6 de
`docs/superpowers/specs/2026-09-17-transport-auth-horizon-design.md`.

**Fait le 17/09** : rattrapage des signatures sur le NUC (44 669 médias en
16 min, pré-filtre désormais actif) ; renommage `mediaserve` → `phototheque` ;
retrait du trieur C++ et de ses sous-modules ; refonte des pages web ; correction
du QR invisible ; README et `DEPLOIEMENT.md` réécrits pas à pas.

## Feuille de route (issues GitHub)
Prochaine étape : **sous-projet 3 = app Android** (issue #12 : scan QR, scan des
dossiers, client d'upload) — commencer par #15, qui fige le contrat qu'elle
codera en dur. Améliorations/Phase 2 tracées en issues #2 à #10 et #14 à #19
(`gh issue list`). Notamment : #4 doublons existants, #5 floues/rafales,
#6 re-datation, #7 sauvegarde Famille.

Le travail de #2, #3, #10 et #14 est **fait** (#8, #9 et #11 sont fermées), mais
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
# Choisir/changer le mot de passe d'administration (sans sudo ni redémarrage) :
./deploy/motdepasse.sh
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
