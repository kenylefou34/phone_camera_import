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
- ✅ **Service `mediaserve/`** (sous-projet 2) : FastAPI, appairage QR, handshake
  anti-doublon, upload, commit (bilan détaillé), page d'admin (appareils +
  camembert disque), mDNS/Avahi, systemd + Docker. Validé sur le NUC.
- ✅ **Déployé en service permanent** (issue #11) : `mediaserve.service` actif et
  `enabled` sur le NUC depuis le 2026-09-14, 0 redémarrage. `/` et `/pair`
  répondent, `/status` exige l'authentification.
- ✅ **Pré-filtre par signature rapide** (issue #9) : le trieur évite la lecture
  intégrale d'un fichier dont la signature est inconnue (~1000× plus rapide sur
  une vidéo de 3 Go : 28,6 s → 0,028 s).
- ✅ **Empreinte calculée pendant la copie** (issue #14) : un fichier rangé n'est
  plus traversé que 2 fois au lieu de 3 (mesuré sur le NUC, vidéo de 3,6 Gio :
  47,9 s → 34,9 s, -27 %). **79 tests**.
- Spécs : `docs/superpowers/specs/` — plans : `docs/superpowers/plans/`.

## ⚠️ À faire sur le NUC (une fois)
Le catalogue existant date d'avant la colonne `signature` : ses 44 669 lignes
l'ont donc vide. Le trieur le détecte et **désactive le pré-filtre** (pour ne
jamais rater un doublon) — il fonctionne comme avant, sans le gain de vitesse.
Pour l'activer, compléter les signatures une bonne fois (~1 h, ne lit que le
début et la fin de chaque média) :
```bash
python3 -m mediasort --catalog ~/mediasort_catalog.db --backfill-signatures
```

## Feuille de route (issues GitHub)
Prochaine étape : **sous-projet 3 = app Android** (issue #12 : scan QR, scan des
dossiers, client d'upload). Améliorations/Phase 2 tracées en issues #2 à #10
et #14 (`gh issue list`). Notamment : #2 horizon de synchro initial,
#3 HTTPS+épinglage, #4 doublons existants, #5 floues/rafales, #6 re-datation,
#7 sauvegarde Famille, #10 durcir la surface d'admin.
(#8, #9, #11 et #14 sont faites.)
À faire aussi : **fusionner `dev` → `main`** — PR #13 ouverte.

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

# Serveur (sur le NUC, venv) :
~/.venv-server/bin/uvicorn mediaserve.app:app --host 0.0.0.0 --port 8787
# puis http://nuc.local:8787/ (admin) et /pair (QR)

# Déploiement : voir deploy/ (mediaserve.service, avahi, Dockerfile) + README.
```

## Binaire C++ existant (`main.cpp`)
Build : `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j2`.
Déps apt : `build-essential cmake libopencv-dev libspdlog-dev libfmt-dev
libboost-all-dev`. ⚠️ Utiliser le **fmt système** (`find_package(fmt)`), pas le
submodule ; inclure `<fmt/std.h>` (fmt ≥ 9). Le trieur Python le remplace.

## Workflow
Skills « superpowers » : brainstorming → spec → plan → TDD. Attribution des
commits : voir les consignes de session.
