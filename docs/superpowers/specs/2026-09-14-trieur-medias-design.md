# Spec — Trieur de médias (Phase 1, sous-projet 1)

*Rédigé le 2026-09-14. Document de conception, en français (l'auteur du projet
débute en Python). Tout le code produit sera commenté et documenté en français.*

---

## 1. Contexte et vision d'ensemble

Refonte de `phone_camera_import`. Objectif final : depuis un téléphone Android
sur le réseau local, synchroniser automatiquement toute la galerie (+ certains
dossiers WhatsApp) vers le NUC, ranger les médias sur un disque dur externe,
classés par **type** (photos / vidéos) et par **date** (`ANNÉE / MOIS`), sans
jamais importer deux fois le même média.

### Phases du projet
- **Phase 1 (en cours)** : le pipeline d'import.
- **Phase 2 (plus tard)** : **consultation en ligne** des médias importés via le
  service web (galerie web, alimentée par l'app de transfert), incluant un
  **outil de révision visuelle** : pour les médias potentiellement mal datés,
  afficher l'image + la date proposée et demander confirmation (oui / non) avant
  de reclasser. Le même outil traite les **doublons déjà présents** dans la
  bibliothèque : proposer lequel garder (confirmation oui / non), en
  **protégeant toujours** les copies rangées dans un dossier curaté (ex.
  `Baptême Paula`), jamais supprimées automatiquement.
- **Phase 3 (plus tard)** : reconnaissance et classement des **visages** (nommer
  les personnes).
- **Phase 4 (plus tard)** : **génération** (ex. « livre photo de 50 images de
  l'année X avec la personne Y »), idées vidéo à définir.

### Découpage de la Phase 1 en 3 sous-projets
1. **LE TRIEUR** (ce spec) — Python, sur le NUC : range un dossier source dans
   la bibliothèque, avec lecture des dates réelles et anti-doublon. Testable
   immédiatement sur les backlogs `unsorted` existants.
2. **LE SERVICE D'INGESTION + DÉCOUVERTE RÉSEAU** — endpoint HTTP qui reçoit les
   fichiers poussés par le téléphone et déclenche le trieur ; mDNS/Avahi pour
   rendre le NUC trouvable (`nuc.local`).
3. **L'APP ANDROID** — application native : scanne les dossiers, dialogue avec
   le NUC pour n'envoyer que le nouveau, bouton « Synchroniser » + case
   « synchro auto sur le wifi maison ».

**Ce spec ne couvre que le sous-projet 1.** Les sous-projets 2 et 3 auront leur
propre cycle conception → spec → implémentation.

---

## 2. Décisions verrouillées (issues du brainstorming)

- **Langage** : Python (choisi pour la lecture de métadonnées, et pour préparer
  la reconnaissance faciale et le web des phases 2-3).
- **Bibliothèque cible** : disque **Famille** (NTFS), monté sur
  `/media/izquierdo/Famille`. Structure conservée à l'identique :
  `Photos/ANNÉE/"MM MOIS"/` et `Videos/ANNÉE/"MM MOIS"/` (ex. `2023/05 MAI`),
  WhatsApp sous `WhatsApp/…`.
- **Anti-doublon** : combinaison *date de dernière synchro par dossier*
  (filtre rapide) **+** *empreinte de contenu* (certitude), via un catalogue
  SQLite tenu sur le NUC.
- **Priorité des dates** : métadonnées > date dans le nom de fichier > date du
  système de fichiers > mise de côté (voir §5).
- **Machine cible** : NUC `izquierdo@192.168.1.21` (IZQUIERDO-NUC), Ubuntu 26.04,
  2 cœurs / 3 Go de RAM. Accès SSH par clé déjà en place.
- **Le backlog `unsorted` n'est PAS supprimé** : il est trié (c'est le premier
  test grandeur nature), puis seul le bruit résiduel est nettoyé.

---

## 3. État des lieux du stockage (constaté sur le NUC)

| Disque | Système de fichiers | Rôle | Santé (SMART) |
|---|---|---|---|
| **Famille** (sdd, NTFS) | lecture/écriture | **bibliothèque cible** (Photos/Videos/ANNÉE/MOIS + `unsorted` de 1643 fichiers) | saine, mais ~5 ans d'alimentation → **backup recommandé** |
| **ELEMENTS** (sdc, FAT32) | **lecture seule** actuellement | archive historique (dossiers d'événements + Musique + sauvegardes) | **matériel sain**, mais **FAT32 corrompu** (chaînes de clusters invalides) → réparable au `fsck.vfat` |
| **Media** (sdb, exfat) | lecture/écriture | 320 Go, presque plein | sain, vieux |

Points liés (hors périmètre de ce spec, mais planifiés) :
- **Réparer ELEMENTS** (`fsck.vfat`) avant de trier son `unsorted` et d'amorcer
  le catalogue depuis son contenu.
- **Stratégie de sauvegarde** de Famille (disque âgé, porteur unique de la
  bibliothèque) — à concevoir séparément ; FAT32 d'ELEMENTS est un mauvais
  candidat en l'état (limite 4 Go par fichier, accents corrompus).

---

## 4. Architecture du trieur

Petit paquet Python, un module = une responsabilité claire, testable isolément.

```
mediasort/
  cli.py         # point d'entrée ligne de commande (arguments, orchestration haut niveau)
  config.py      # constantes : extensions, exclusions WhatsApp, noms de mois FR, motifs de bruit
  dates.py       # résolution de la date d'un média (métadonnées / nom / système de fichiers)
  hashing.py     # empreinte de contenu d'un fichier
  catalog.py     # catalogue SQLite (anti-doublon, amorçage, état de synchro)
  classify.py    # décision du chemin de destination (type, WhatsApp, ANNÉE/MOIS)
  noise.py       # détection et nettoyage du bruit résiduel
  sorter.py      # orchestration : parcours source -> plan d'action -> exécution sûre -> journal
tests/           # tests unitaires (voir §11)
```

**Flux de données pour un fichier source :**

```
fichier
  │
  ├─ extension connue ? (config.py)  ── non ─▶ ignoré (journalisé)
  │
  ├─ empreinte (hashing.py) ─▶ déjà au catalogue ? (catalog.py) ── oui ─▶ DOUBLON (non rangé)
  │
  ├─ date réelle (dates.py) : métadonnées ▶ nom ▶ système de fichiers ▶ inconnue
  │
  ├─ destination (classify.py) : Photos|Videos [/WhatsApp] / ANNÉE / "MM MOIS"
  │       (date inconnue ─▶ dossier `_A_TRIER/`)
  │
  └─ exécution sûre (sorter.py) : copie ▶ vérifie l'empreinte à destination ▶
        enregistre au catalogue ▶ retire la source
```

---

## 5. Résolution de la date (le cœur)

Pour chaque fichier, on prend la **première date fiable** trouvée dans cet
ordre :

| Priorité | Source | Mise en œuvre |
|---|---|---|
| 1 | **Métadonnées de prise de vue** | `exiftool` (photos ET vidéos, tous formats dont HEIC/DNG) ; `ffprobe` en secours pour la vidéo. On lit `DateTimeOriginal` / `CreateDate` / `creation_time`. |
| 2 | **Date encodée dans le nom** | Analyse de motifs courants : `IMG_20230526…`, `VID-20230526-WA…`, `PXL_20230526…`, `Signal-2023-05-26…`, `Screenshot_2023-05-26…`, etc. |
| 3 | **Date du système de fichiers** | `os.stat` (date de modification). Peu fiable après recopie, d'où sa 3ᵉ place. |
| 4 | **Inconnue** | Aucun classement au hasard : le fichier va dans `_A_TRIER/` pour un tri manuel ultérieur. |

**Justification du choix « nom avant système de fichiers » :** les backlogs sont
des copies ; la date du système de fichiers a souvent été écrasée par la copie,
alors que la date dans le nom survit. Sur ces dumps, le nom est plus fiable.

Chaque date résolue est journalisée **avec sa source** (métadonnées / nom /
système / inconnue) pour pouvoir auditer le classement.

---

## 6. Taxonomie de rangement (identique à l'existant)

- Photo → `Photos/ANNÉE/"MM MOIS"/` (ex. `Photos/2023/05 MAI/`).
- Vidéo → `Videos/ANNÉE/"MM MOIS"/`.
- Média WhatsApp → sous `WhatsApp/…` avec les **mêmes exclusions** que le C++
  actuel : `Sent`, `WhatsApp Animated Gifs`, `WhatsApp Documents`,
  `WhatsApp Stickers`, `WhatsApp Video Notes`.
- Mois en français, majuscules, préfixe numérique sur 2 chiffres (voir
  `config.py`).
- **On ne touche jamais** aux dossiers d'événements curatés à la main
  (`02 - CANARIAS`, `Mariage …`, etc.). Le trieur ne fait qu'ajouter dans les
  dossiers `ANNÉE/"MM MOIS"` standard.
- **Définition « dossier curaté »** : tout dossier album dont le nom ne suit pas
  le motif standard `ANNÉE` (ex. `2023`) ou `"MM MOIS"` (ex. `05 MAI`) — par
  exemple `Baptême Paula`, `02 - CANARIAS`. Le trieur n'y écrit jamais, n'en
  supprime jamais rien, et la Phase 2 y protège les doublons.
- **WhatsApp** : rangé en `WhatsApp/Photos|Videos/ANNÉE/"MM MOIS"/`, uniformisé
  avec le reste (l'existant `WhatsApp/Photos` par année seule coexistera ; le
  catalogue empêche les doublons).
- Date inconnue → `_A_TRIER/` (à la racine de la bibliothèque).

Extensions gérées (reprises de l'existant, ajustables dans `config.py`) :
- Photos : `.png .jpg .jpeg .bmp .dng .heic .webp`
- Vidéos : `.mp4 .mkv .avi .mov .m4v .wmv .3gp` (+ audio associé selon besoin).

---

## 7. Anti-doublon : le catalogue SQLite

Base unique sur le NUC (ex. `~/.local/share/mediasort/catalog.db`).

**Table `medias`** (un enregistrement par média présent en bibliothèque) :

| colonne | rôle |
|---|---|
| `empreinte` | hash du contenu (clé d'unicité) |
| `taille` | taille en octets (pré-filtre rapide avant hash) |
| `chemin` | emplacement en bibliothèque |
| `date_prise` | date retenue |
| `source_date` | métadonnées / nom / système / inconnue |
| `date_import` | quand le média a été rangé |

**Table `synchros`** : date de dernière synchro **par dossier source**
(amorcée au 1er run depuis les anciens fichiers `.flagfile_timestamp` s'ils
existent — filtre rapide « ne regarder que le nouveau »).

**Amorçage (1er run)** : scan de la bibliothèque existante (Famille, puis
ELEMENTS réparé) pour pré-remplir `medias`. Ainsi tout ce qui est déjà classé
— y compris à la main dans des dossiers d'événements — est reconnu et **jamais
réimporté**.

**Empreinte** : `hashlib` (stdlib). Pré-filtre par taille pour éviter de hasher
inutilement ; hash complet sur les candidats de même taille. (Optimisation
possible plus tard : hash partiel début/fin pour les très grosses vidéos.)

**Doublons déjà présents** : l'amorçage détecte naturellement les empreintes en
double dans la bibliothèque existante. Ils sont **signalés** (jamais supprimés
par le trieur) pour la révision visuelle de la Phase 2, qui protège toujours les
copies en dossier curaté. Le champ `source_date` sert aussi cette phase : les
médias datés par une source faible (nom, système de fichiers, `_A_TRIER`) sont
les candidats prioritaires à la révision visuelle.

---

## 8. Nettoyage du bruit (sécurisé, après tri)

Une fois les vrais médias extraits d'`unsorted`, il reste :
- du bruit connu : `.opus` (vocaux WhatsApp), `.crypt14` (bases chiffrées),
  `.nomedia`, dossiers `.links`, dossiers vides ;
- des **doublons certifiés** (déjà au catalogue par empreinte).

Règle : **jamais de suppression en aveugle.** Le trieur supprime uniquement les
motifs de bruit connus (liste dans `noise.py`) et les doublons prouvés par
empreinte, et seulement après le mode simulation validé.

---

## 9. Robustesse

- **Mode simulation (`--dry-run`)** : parcourt et journalise le plan complet
  sans rien déplacer. Utilisé d'abord sur les gros lots.
- **Copie sûre** : on copie vers la destination, on **revérifie l'empreinte**,
  on enregistre au catalogue, **puis seulement** on retire la source. Aucune
  perte si le processus est interrompu.
- **Journal en français** : pour chaque fichier — rangé (avec destination et
  source de date) / doublon ignoré / mis en `_A_TRIER` / bruit supprimé /
  erreur. Résumé final (compteurs).
- **Particularités NTFS** (Famille) : assainissement des noms (caractères
  réservés), attention à la casse (NTFS insensible à la casse).
- **Idempotence** : relancer le trieur sur la même source ne crée pas de
  doublons (le catalogue tranche).

---

## 10. Interface en ligne de commande (esquisse)

```
python -m mediasort \
    --source  /media/izquierdo/Famille/unsorted \
    --library /media/izquierdo/Famille \
    [--dry-run]          # simulation : ne rien déplacer
    [--seed]             # amorcer le catalogue depuis la bibliothèque existante
    [--clean-noise]      # supprimer le bruit résiduel après tri (sécurisé)
    [--verbose]
```

---

## 11. Plan de test

- **Tests unitaires** (TDD) sur les modules purs, sans I/O réseau/disque lourd :
  - `dates.py` : chaque motif de nom, priorité des sources, cas « inconnue ».
  - `classify.py` : chemins de destination, détection + exclusions WhatsApp.
  - `hashing.py` / `catalog.py` : unicité, détection de doublon, amorçage.
  - `noise.py` : motifs de bruit reconnus vs vrais médias préservés.
- **Jeu de fixtures** : petits fichiers factices avec dates/n­oms contrôlés
  (comme le test manuel déjà réalisé avec le binaire C++).
- **Test grandeur nature** : `Famille/unsorted` (1643 fichiers) en `--dry-run`,
  lecture du rapport ensemble, puis exécution réelle ; ensuite ELEMENTS après
  réparation `fsck`.

---

## 12. Environnement et dépendances

- **Python** : 3.x (déjà présent sur le NUC), exécuté dans un **virtualenv**
  (`python3 -m venv`), dépendances installées par `pip` (sans sudo).
- **Bibliothèque standard suffisante** pour l'essentiel : `sqlite3`, `hashlib`,
  `pathlib`, `os`, `argparse`, `subprocess`, `re`, `logging`.
- **Outils système** (via `apt`, sudo) :
  - `libimage-exiftool-perl` (exiftool) — lecture des dates de prise de vue.
  - `ffmpeg` (ffprobe) — secours pour les dates vidéo.
  - `python3-venv`, `python3-pip` si absents.
- La documentation d'installation et d'utilisation ira dans le **README**
  (section « Mise en place de l'environnement » + « Utilisation »), rédigée lors
  de l'implémentation.

---

## 13. Hors périmètre de ce spec (mais planifié)

- Service d'ingestion HTTP + découverte mDNS (sous-projet 2).
- Application Android (sous-projet 3).
- Réparation `fsck` d'ELEMENTS et stratégie de sauvegarde de Famille (tâches
  d'administration système, à traiter en parallèle).
- Reconnaissance faciale, web, génération (phases 2-3).

---

## 14. Questions résolues / restantes

**Résolues :** langage (Python), cible (Famille), format des dossiers
(`ANNÉE/"MM MOIS"` conservé), priorité des dates (nom avant système de
fichiers), anti-doublon (timestamp + empreinte), sort du backlog (trié, pas
supprimé), outils métadonnées (exiftool + ffprobe), **WhatsApp uniformisé en
`ANNÉE/"MM MOIS"`**, extensions (`.webp` côté photos, audio pur écarté), bac
`_A_TRIER/` pour les dates non fiables.

**Restantes / à confirmer à la relecture :**
- Emplacement exact du catalogue et de la bibliothèque à passer en paramètres
  (valeurs par défaut proposées ci-dessus).
