# CLAUDE.md — phone_camera_import

Orientation pour les sessions Claude Code sur ce dépôt.

## Langue
Le mainteneur débute en Python : **documenter et commenter le code en français**,
explications accessibles.

## Ce qu'est le projet
Outil d'import de médias (photos/vidéos) d'un téléphone vers une bibliothèque
rangée par type et par date (`ANNÉE / "MM MOIS"`, mois en français).

- **Existant** : `main.cpp` (binaire C++ `phone_camera_import`) qui trie par date
  de dernière modification, et `run_backup.sh` (récupération rsync/SSH depuis un
  téléphone via SimpleSSHD).
- **Refonte en cours** (branche `dev`) : reconstruction en Python avec lecture
  des vraies dates de prise de vue (EXIF/vidéo), anti-doublon par empreinte, puis
  app Android + reconnaissance faciale + génération. Voir les specs.

## Specs / conception
- `docs/superpowers/specs/` — documents de conception. Point d'entrée actuel :
  `2026-09-14-trieur-medias-design.md` (Phase 1, sous-projet « trieur »).

## Machine cible (NUC)
- SSH par clé : `ssh izquierdo@192.168.1.21` (hôte `IZQUIERDO-NUC`, Ubuntu 26.04,
  2 cœurs / 3 Go). `sudo` demande un mot de passe → passer par un vrai terminal
  (le canal `!` de Claude Code n'a pas de TTY) ou un `sudoers.d` restreint.
- Bibliothèque médias sur disques externes : **Famille** (NTFS,
  `/media/izquierdo/Famille`) = cible ; **ELEMENTS** (FAT32, souvent monté en
  lecture seule car FAT corrompu — réparable au `fsck.vfat`) = archive ;
  **Media** (exfat) = 320 Go presque plein.
- Structure bibliothèque : `Photos/ANNÉE/"MM MOIS"/`, `Videos/…`, `WhatsApp/…`,
  `unsorted/` (backlog à trier). Ne pas toucher aux dossiers d'événements
  curatés à la main (ex. `2022/02 - CANARIAS`).

## Build du binaire C++ (existant)
Dépendances système (apt) : `build-essential cmake libopencv-dev libspdlog-dev
libfmt-dev libboost-all-dev`. Submodule header-only : CLI11.

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
```

⚠️ Piège déjà corrigé : utiliser le **fmt système** (`find_package(fmt)`), pas le
submodule `modules/fmt` (8.1.1) qui casse le link avec le spdlog système (fmt 10).
Depuis fmt ≥ 9, inclure `<fmt/std.h>` pour formater `std::filesystem::path` et
fournir un `ostream_formatter` pour les types à `operator<<`.

## Workflow
- Skills « superpowers » actives (brainstorming avant conception, TDD avant code,
  etc.). Suivre le cycle conception → spec → plan → implémentation.
- Attribution des commits : voir les consignes de session.
