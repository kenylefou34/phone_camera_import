# Plan d'implémentation — Trieur de médias

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire `mediasort`, un outil Python qui range un dossier source de photos/vidéos dans une bibliothèque `Photos|Videos/ANNÉE/"MM MOIS"`, en lisant la vraie date de prise de vue et sans jamais créer de doublon.

**Architecture:** Petit paquet Python (un module = une responsabilité), sans framework. Les dates viennent d'`exiftool`/`ffprobe` (sous-processus), le reste est en bibliothèque standard (`sqlite3`, `hashlib`, `pathlib`, `re`, `argparse`). Développement piloté par les tests (pytest), commits fréquents.

**Tech Stack:** Python 3 (stdlib) ; outils système `exiftool` + `ffprobe` ; tests `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-14-trieur-medias-design.md`

## Global Constraints

- **Documentation et commentaires en français** (le mainteneur débute en Python).
- **Bibliothèque standard d'abord** ; seules dépendances système : `exiftool`, `ffprobe` (déjà installés sur le NUC).
- **Format des dossiers mois** : exactement `"MM MOIS"` en français majuscule, ex. `05 MAI` (préfixe numérique 2 chiffres).
- **Priorité des dates** : métadonnées → nom de fichier → système de fichiers → `_A_TRIER/`.
- **Dossiers curatés** (nom ≠ `ANNÉE` ni `"MM MOIS"`) : jamais écrits, jamais supprimés.
- **Copie sûre** : copier → vérifier l'empreinte à destination → enregistrer au catalogue → seulement ensuite retirer la source.
- **Jamais de suppression en aveugle** : seuls le bruit connu et les doublons certifiés par empreinte.
- **Mode simulation (`--dry-run`)** : ne déplace/supprime rien.
- **Extensions** : photos `.png .jpg .jpeg .bmp .dng .heic .webp` ; vidéos `.mp4 .mkv .avi .mov .m4v .wmv .3gp`.
- **Exclusions WhatsApp** : `Sent`, `WhatsApp Animated Gifs`, `WhatsApp Documents`, `WhatsApp Stickers`, `WhatsApp Video Notes`.

---

## Structure des fichiers

```
mediasort/
  __init__.py
  config.py     # constantes + month_folder()
  dates.py      # date_from_filename / date_from_metadata / resolve_date
  hashing.py    # file_hash
  catalog.py    # class Catalog (SQLite)
  classify.py   # media_type / is_whatsapp / is_excluded / is_curated_folder / destination
  noise.py      # is_noise / clean_noise
  sorter.py     # sort_folder (orchestration) + Report
  cli.py        # main() : arguments et câblage
tests/
  test_config.py test_dates.py test_hashing.py test_catalog.py
  test_classify.py test_noise.py test_sorter.py test_cli.py
requirements-dev.txt   # pytest
README.md              # complété : mise en place + utilisation (français)
```

---

### Task 1: Échafaudage du projet + `config.py`

**Files:**
- Create: `requirements-dev.txt`, `mediasort/__init__.py`, `mediasort/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: rien.
- Produces: `config.PHOTO_EXTS: set[str]`, `config.VIDEO_EXTS: set[str]`, `config.WHATSAPP_EXCLUDES: list[str]`, `config.NOISE_EXTS: set[str]`, `config.MONTHS_FR: dict[int,str]`, `config.month_folder(month: int) -> str`.

- [ ] **Step 1: Créer l'environnement et la dépendance de test**

```bash
cd /home/invisart/dev/phone_camera_import
python3 -m venv .venv
. .venv/bin/activate
printf "pytest\n" > requirements-dev.txt
pip install -r requirements-dev.txt
mkdir -p mediasort tests
: > mediasort/__init__.py
```

- [ ] **Step 2: Écrire le test qui échoue**

```python
# tests/test_config.py
from mediasort import config


def test_month_folder_format():
    assert config.month_folder(5) == "05 MAI"
    assert config.month_folder(12) == "12 DECEMBRE"
    assert config.month_folder(1) == "01 JANVIER"


def test_extension_sets_are_lowercase_with_dot():
    assert ".jpg" in config.PHOTO_EXTS
    assert ".mp4" in config.VIDEO_EXTS
    assert config.PHOTO_EXTS.isdisjoint(config.VIDEO_EXTS)
```

- [ ] **Step 3: Lancer le test et vérifier l'échec**

Run: `. .venv/bin/activate && python -m pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError` / `AttributeError`).

- [ ] **Step 4: Écrire `config.py`**

```python
# mediasort/config.py
"""Constantes de configuration du trieur (extensions, mois, exclusions)."""

# Extensions reconnues (toujours en minuscules, avec le point).
PHOTO_EXTS: set[str] = {".png", ".jpg", ".jpeg", ".bmp", ".dng", ".heic", ".webp"}
VIDEO_EXTS: set[str] = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv", ".3gp"}

# Bruit à ne jamais ranger (nettoyé séparément, voir noise.py).
NOISE_EXTS: set[str] = {".opus", ".crypt14", ".nomedia"}

# Sous-dossiers WhatsApp volontairement exclus.
WHATSAPP_EXCLUDES: list[str] = [
    "Sent",
    "WhatsApp Animated Gifs",
    "WhatsApp Documents",
    "WhatsApp Stickers",
    "WhatsApp Video Notes",
]

# Mois en français (majuscules), pour les dossiers "MM MOIS".
MONTHS_FR: dict[int, str] = {
    1: "JANVIER", 2: "FEVRIER", 3: "MARS", 4: "AVRIL",
    5: "MAI", 6: "JUIN", 7: "JUILLET", 8: "AOUT",
    9: "SEPTEMBRE", 10: "OCTOBRE", 11: "NOVEMBRE", 12: "DECEMBRE",
}


def month_folder(month: int) -> str:
    """Renvoie le nom de dossier d'un mois, ex. 5 -> "05 MAI"."""
    return f"{month:02d} {MONTHS_FR[month]}"
```

- [ ] **Step 5: Lancer le test et vérifier le succès**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt mediasort/__init__.py mediasort/config.py tests/test_config.py
git commit -m "feat(mediasort): échafaudage + config (extensions, mois)"
```

---

### Task 2: `dates.py` — date depuis le nom de fichier

**Files:**
- Create: `mediasort/dates.py`
- Test: `tests/test_dates.py`

**Interfaces:**
- Consumes: rien.
- Produces: `dates.date_from_filename(name: str) -> datetime.date | None`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_dates.py
import datetime
from mediasort import dates


def test_date_from_filename_patterns():
    d = datetime.date(2023, 5, 26)
    assert dates.date_from_filename("IMG_20230526_101500.jpg") == d
    assert dates.date_from_filename("VID-20230526-WA0009.mp4") == d
    assert dates.date_from_filename("PXL_20230526_101500123.jpg") == d
    assert dates.date_from_filename("Screenshot_2023-05-26-10-15.png") == d
    assert dates.date_from_filename("signal-2023-05-26-101500.jpg") == d


def test_date_from_filename_none_when_absent():
    assert dates.date_from_filename("photo_sans_date.jpg") is None


def test_date_from_filename_rejects_impossible_dates():
    # 2023-13-40 n'est pas une date valide -> None
    assert dates.date_from_filename("IMG_20231340.jpg") is None
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python -m pytest tests/test_dates.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire la fonction**

```python
# mediasort/dates.py
"""Résolution de la date d'un média : métadonnées, nom de fichier, système."""

import datetime
import re

# Capture AAAA MM JJ avec séparateurs optionnels (-, _, .).
_FILENAME_DATE_RE = re.compile(
    r"((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
)


def date_from_filename(name: str) -> datetime.date | None:
    """Extrait la première date valide encodée dans le nom, sinon None."""
    for match in _FILENAME_DATE_RE.finditer(name):
        annee, mois, jour = (int(g) for g in match.groups())
        try:
            return datetime.date(annee, mois, jour)
        except ValueError:
            continue
    return None
```

- [ ] **Step 4: Lancer le test et vérifier le succès**

Run: `python -m pytest tests/test_dates.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediasort/dates.py tests/test_dates.py
git commit -m "feat(dates): extraction de date depuis le nom de fichier"
```

---

### Task 3: `dates.py` — date depuis les métadonnées (exiftool)

**Files:**
- Modify: `mediasort/dates.py`
- Test: `tests/test_dates.py`

**Interfaces:**
- Consumes: rien.
- Produces: `dates._pick_metadata_date(tags: dict) -> datetime.date | None`, `dates.date_from_metadata(path: pathlib.Path) -> datetime.date | None`.

- [ ] **Step 1: Écrire le test qui échoue (logique pure de sélection)**

```python
# tests/test_dates.py  (ajouter)
def test_pick_metadata_date_priority():
    tags = {
        "DateTimeOriginal": "2023:05:26 10:15:00",
        "CreateDate": "2020:01:01 00:00:00",
    }
    assert dates._pick_metadata_date(tags) == datetime.date(2023, 5, 26)


def test_pick_metadata_date_fallback_createdate():
    tags = {"CreateDate": "2019:07:04 12:00:00"}
    assert dates._pick_metadata_date(tags) == datetime.date(2019, 7, 4)


def test_pick_metadata_date_ignore_zero():
    # exiftool renvoie parfois des dates nulles -> ignorées
    tags = {"DateTimeOriginal": "0000:00:00 00:00:00"}
    assert dates._pick_metadata_date(tags) is None


def test_pick_metadata_date_empty():
    assert dates._pick_metadata_date({}) is None
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python -m pytest tests/test_dates.py::test_pick_metadata_date_priority -v`
Expected: FAIL (`AttributeError: _pick_metadata_date`).

- [ ] **Step 3: Écrire la sélection + l'appel exiftool**

```python
# mediasort/dates.py  (ajouter en tête les imports)
import json
import subprocess
from pathlib import Path

# Ordre de préférence des balises de date renvoyées par exiftool.
_METADATA_TAGS = [
    "DateTimeOriginal",   # photos
    "CreateDate",         # photos et vidéos
    "CreationDate",       # vidéos (QuickTime)
    "MediaCreateDate",    # vidéos
]


def _pick_metadata_date(tags: dict) -> "datetime.date | None":
    """Choisit la meilleure date parmi les balises exiftool (ordre de préférence)."""
    for cle in _METADATA_TAGS:
        valeur = tags.get(cle)
        if not valeur:
            continue
        # Format attendu : "AAAA:MM:JJ hh:mm:ss" (parfois avec fuseau derrière).
        debut = str(valeur)[:10]  # "AAAA:MM:JJ"
        try:
            annee, mois, jour = (int(x) for x in debut.split(":"))
            return datetime.date(annee, mois, jour)
        except (ValueError, TypeError):
            continue
    return None


def _exiftool_tags(path: Path) -> dict:
    """Interroge exiftool et renvoie un dict de balises (vide en cas d'échec)."""
    try:
        sortie = subprocess.run(
            ["exiftool", "-json", "-api", "QuickTimeUTC",
             *[f"-{t}" for t in _METADATA_TAGS], str(path)],
            capture_output=True, text=True, timeout=30, check=False,
        )
        donnees = json.loads(sortie.stdout or "[]")
        return donnees[0] if donnees else {}
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return {}


def date_from_metadata(path: Path) -> "datetime.date | None":
    """Renvoie la date de prise de vue lue dans les métadonnées, sinon None."""
    return _pick_metadata_date(_exiftool_tags(path))
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python -m pytest tests/test_dates.py -v`
Expected: PASS (tous).

- [ ] **Step 5: Commit**

```bash
git add mediasort/dates.py tests/test_dates.py
git commit -m "feat(dates): lecture de la date de prise de vue via exiftool"
```

---

### Task 4: `dates.py` — `resolve_date` (priorité complète)

**Files:**
- Modify: `mediasort/dates.py`
- Test: `tests/test_dates.py`

**Interfaces:**
- Consumes: `date_from_filename`, `date_from_metadata`.
- Produces: `dates.DateResult` (namedtuple `(date, source)`, `source ∈ {"metadata","filename","filesystem","unknown"}`), `dates.resolve_date(path: pathlib.Path) -> DateResult`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_dates.py  (ajouter)
import pathlib


def test_resolve_date_prefers_metadata(monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    r = dates.resolve_date(pathlib.Path("IMG_20200101.jpg"))
    assert r.date == datetime.date(2023, 5, 26)
    assert r.source == "metadata"


def test_resolve_date_falls_back_to_filename(monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: None)
    r = dates.resolve_date(pathlib.Path("IMG_20230526.jpg"))
    assert r.date == datetime.date(2023, 5, 26)
    assert r.source == "filename"


def test_resolve_date_falls_back_to_filesystem(tmp_path, monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: None)
    f = tmp_path / "sans_date.jpg"
    f.write_bytes(b"x")
    r = dates.resolve_date(f)
    assert r.source == "filesystem"
    assert isinstance(r.date, datetime.date)


def test_resolve_date_unknown_when_missing_file(monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: None)
    r = dates.resolve_date(pathlib.Path("/inexistant/sans_date.jpg"))
    assert r.source == "unknown"
    assert r.date is None
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python -m pytest tests/test_dates.py::test_resolve_date_prefers_metadata -v`
Expected: FAIL (`AttributeError: resolve_date`).

- [ ] **Step 3: Écrire `resolve_date` + `DateResult` + date système**

```python
# mediasort/dates.py  (ajouter)
from collections import namedtuple

DateResult = namedtuple("DateResult", ["date", "source"])


def date_from_filesystem(path: Path) -> "datetime.date | None":
    """Date de dernière modification du fichier, ou None s'il est illisible."""
    try:
        horodatage = path.stat().st_mtime
    except OSError:
        return None
    return datetime.date.fromtimestamp(horodatage)


def resolve_date(path: Path) -> DateResult:
    """Résout la date selon la priorité : métadonnées > nom > système > inconnue."""
    d = date_from_metadata(path)
    if d is not None:
        return DateResult(d, "metadata")
    d = date_from_filename(path.name)
    if d is not None:
        return DateResult(d, "filename")
    d = date_from_filesystem(path)
    if d is not None:
        return DateResult(d, "filesystem")
    return DateResult(None, "unknown")
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python -m pytest tests/test_dates.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediasort/dates.py tests/test_dates.py
git commit -m "feat(dates): resolve_date avec priorité métadonnées/nom/système"
```

---

### Task 5: `hashing.py` — empreinte de contenu

**Files:**
- Create: `mediasort/hashing.py`
- Test: `tests/test_hashing.py`

**Interfaces:**
- Consumes: rien.
- Produces: `hashing.file_hash(path: pathlib.Path) -> str` (sha256 hexadécimal).

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_hashing.py
import hashlib
from mediasort import hashing


def test_file_hash_matches_hashlib(tmp_path):
    f = tmp_path / "a.bin"
    contenu = b"bonjour" * 1000
    f.write_bytes(contenu)
    assert hashing.file_hash(f) == hashlib.sha256(contenu).hexdigest()


def test_file_hash_differs_for_different_content(tmp_path):
    a = tmp_path / "a.bin"; a.write_bytes(b"aaa")
    b = tmp_path / "b.bin"; b.write_bytes(b"bbb")
    assert hashing.file_hash(a) != hashing.file_hash(b)
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python -m pytest tests/test_hashing.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire la fonction**

```python
# mediasort/hashing.py
"""Empreinte de contenu d'un fichier (SHA-256), lue par blocs."""

import hashlib
from pathlib import Path

_BLOC = 1024 * 1024  # 1 Mio


def file_hash(path: Path) -> str:
    """Renvoie l'empreinte SHA-256 hexadécimale du contenu du fichier."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloc in iter(lambda: f.read(_BLOC), b""):
            h.update(bloc)
    return h.hexdigest()
```

- [ ] **Step 4: Lancer le test et vérifier le succès**

Run: `python -m pytest tests/test_hashing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediasort/hashing.py tests/test_hashing.py
git commit -m "feat(hashing): empreinte SHA-256 par blocs"
```

---

### Task 6: `catalog.py` — catalogue SQLite

**Files:**
- Create: `mediasort/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `hashing.file_hash`, `config.PHOTO_EXTS`, `config.VIDEO_EXTS`.
- Produces: `catalog.Catalog` avec :
  - `__init__(self, db_path)` (`":memory:"` accepté)
  - `has_hash(self, digest: str) -> bool`
  - `add_media(self, digest: str, size: int, path: str, date_prise: str | None, source_date: str) -> None`
  - `count(self) -> int`
  - `seed_from_library(self, library: pathlib.Path) -> int`
  - `get_last_sync(self, folder: str) -> float | None`
  - `set_last_sync(self, folder: str, ts: float) -> None`
  - `close(self) -> None`

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_catalog.py
from mediasort.catalog import Catalog


def test_add_and_has_hash():
    cat = Catalog(":memory:")
    assert cat.has_hash("abc") is False
    cat.add_media("abc", 10, "/lib/x.jpg", "2023-05-26", "metadata")
    assert cat.has_hash("abc") is True
    assert cat.count() == 1
    cat.close()


def test_add_media_is_idempotent_on_hash():
    cat = Catalog(":memory:")
    cat.add_media("abc", 10, "/lib/x.jpg", "2023-05-26", "metadata")
    cat.add_media("abc", 10, "/lib/copie.jpg", "2023-05-26", "metadata")
    assert cat.count() == 1
    cat.close()


def test_last_sync_roundtrip():
    cat = Catalog(":memory:")
    assert cat.get_last_sync("Camera") is None
    cat.set_last_sync("Camera", 1234.5)
    assert cat.get_last_sync("Camera") == 1234.5
    cat.close()


def test_seed_from_library_indexes_media(tmp_path):
    (tmp_path / "Photos" / "2023").mkdir(parents=True)
    (tmp_path / "Photos" / "2023" / "a.jpg").write_bytes(b"photo-a")
    (tmp_path / "notes.txt").write_bytes(b"pas un media")
    cat = Catalog(":memory:")
    n = cat.seed_from_library(tmp_path)
    assert n == 1  # seule a.jpg est indexée
    assert cat.count() == 1
    cat.close()
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire la classe**

```python
# mediasort/catalog.py
"""Catalogue SQLite : anti-doublon par empreinte + dates de synchro par dossier."""

import sqlite3
from pathlib import Path

from . import config
from .hashing import file_hash

_MEDIA_EXTS = config.PHOTO_EXTS | config.VIDEO_EXTS


class Catalog:
    """Mémoire persistante des médias déjà en bibliothèque."""

    def __init__(self, db_path) -> None:
        self._cx = sqlite3.connect(str(db_path))
        self._cx.execute(
            "CREATE TABLE IF NOT EXISTS medias ("
            " empreinte TEXT PRIMARY KEY, taille INTEGER, chemin TEXT,"
            " date_prise TEXT, source_date TEXT, date_import TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self._cx.execute(
            "CREATE TABLE IF NOT EXISTS synchros ("
            " dossier TEXT PRIMARY KEY, dernier_ts REAL)"
        )
        self._cx.commit()

    def has_hash(self, digest: str) -> bool:
        cur = self._cx.execute("SELECT 1 FROM medias WHERE empreinte=?", (digest,))
        return cur.fetchone() is not None

    def add_media(self, digest: str, size: int, path: str,
                  date_prise, source_date: str) -> None:
        # INSERT OR IGNORE : une empreinte n'est enregistrée qu'une fois.
        self._cx.execute(
            "INSERT OR IGNORE INTO medias"
            " (empreinte, taille, chemin, date_prise, source_date)"
            " VALUES (?,?,?,?,?)",
            (digest, size, path, date_prise, source_date),
        )
        self._cx.commit()

    def count(self) -> int:
        return self._cx.execute("SELECT COUNT(*) FROM medias").fetchone()[0]

    def seed_from_library(self, library: Path) -> int:
        """Indexe tous les médias déjà présents en bibliothèque. Renvoie le nombre ajouté."""
        ajoutes = 0
        for p in library.rglob("*"):
            if p.is_file() and p.suffix.lower() in _MEDIA_EXTS:
                digest = file_hash(p)
                if not self.has_hash(digest):
                    self.add_media(digest, p.stat().st_size, str(p), None, "seed")
                    ajoutes += 1
        return ajoutes

    def get_last_sync(self, folder: str):
        cur = self._cx.execute("SELECT dernier_ts FROM synchros WHERE dossier=?", (folder,))
        ligne = cur.fetchone()
        return ligne[0] if ligne else None

    def set_last_sync(self, folder: str, ts: float) -> None:
        self._cx.execute(
            "INSERT INTO synchros (dossier, dernier_ts) VALUES (?,?)"
            " ON CONFLICT(dossier) DO UPDATE SET dernier_ts=excluded.dernier_ts",
            (folder, ts),
        )
        self._cx.commit()

    def close(self) -> None:
        self._cx.close()
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediasort/catalog.py tests/test_catalog.py
git commit -m "feat(catalog): catalogue SQLite (anti-doublon + synchros)"
```

---

### Task 7: `classify.py` — chemin de destination

**Files:**
- Create: `mediasort/classify.py`
- Test: `tests/test_classify.py`

**Interfaces:**
- Consumes: `config`, `dates.DateResult`.
- Produces:
  - `classify.media_type(ext: str) -> str | None` (`"photo"` / `"video"` / `None`)
  - `classify.is_whatsapp(path: pathlib.Path) -> bool`
  - `classify.is_excluded(path: pathlib.Path) -> bool`
  - `classify.is_curated_folder(name: str) -> bool`
  - `classify.destination(library: pathlib.Path, source_file: pathlib.Path, date_result, mtype: str) -> pathlib.Path`

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_classify.py
import datetime
import pathlib
from mediasort import classify
from mediasort.dates import DateResult


def test_media_type():
    assert classify.media_type(".JPG") == "photo"
    assert classify.media_type(".mp4") == "video"
    assert classify.media_type(".txt") is None


def test_is_whatsapp_and_excluded():
    assert classify.is_whatsapp(pathlib.Path("/x/WhatsApp Images/IMG.jpg")) is True
    assert classify.is_whatsapp(pathlib.Path("/x/Camera/IMG.jpg")) is False
    assert classify.is_excluded(pathlib.Path("/x/WhatsApp/Sent/IMG.jpg")) is True
    assert classify.is_excluded(pathlib.Path("/x/WhatsApp Images/IMG.jpg")) is False


def test_is_curated_folder():
    assert classify.is_curated_folder("2023") is False
    assert classify.is_curated_folder("05 MAI") is False
    assert classify.is_curated_folder("Bapteme Paula") is True
    assert classify.is_curated_folder("02 - CANARIAS") is True


def test_destination_photo():
    lib = pathlib.Path("/lib")
    src = pathlib.Path("/src/Camera/IMG_20230526.jpg")
    dr = DateResult(datetime.date(2023, 5, 26), "metadata")
    assert classify.destination(lib, src, dr, "photo") == \
        pathlib.Path("/lib/Photos/2023/05 MAI/IMG_20230526.jpg")


def test_destination_whatsapp_video():
    lib = pathlib.Path("/lib")
    src = pathlib.Path("/src/WhatsApp Video/VID-20230526-WA0009.mp4")
    dr = DateResult(datetime.date(2023, 5, 26), "filename")
    assert classify.destination(lib, src, dr, "video") == \
        pathlib.Path("/lib/WhatsApp/Videos/2023/05 MAI/VID-20230526-WA0009.mp4")


def test_destination_unknown_goes_to_triage():
    lib = pathlib.Path("/lib")
    src = pathlib.Path("/src/Camera/mystere.jpg")
    dr = DateResult(None, "unknown")
    assert classify.destination(lib, src, dr, "photo") == \
        pathlib.Path("/lib/_A_TRIER/mystere.jpg")
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python -m pytest tests/test_classify.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire le module**

```python
# mediasort/classify.py
"""Décision du chemin de destination d'un média dans la bibliothèque."""

import re
from pathlib import Path

from . import config

# Un dossier "standard" est soit une année (ex. 2023), soit "MM MOIS" (ex. 05 MAI).
_ANNEE_RE = re.compile(r"^(?:19|20)\d{2}$")
_MOIS_RE = re.compile(r"^(0[1-9]|1[0-2]) [A-ZÉÈ]+$")


def media_type(ext: str) -> "str | None":
    """Renvoie 'photo', 'video' ou None selon l'extension (insensible à la casse)."""
    e = ext.lower()
    if e in config.PHOTO_EXTS:
        return "photo"
    if e in config.VIDEO_EXTS:
        return "video"
    return None


def is_whatsapp(path: Path) -> bool:
    """Vrai si l'un des dossiers du chemin évoque WhatsApp."""
    return any("whatsapp" in part.lower() for part in path.parts)


def is_excluded(path: Path) -> bool:
    """Vrai si le chemin traverse un sous-dossier WhatsApp exclu."""
    parts = set(path.parts)
    return any(excl in parts for excl in config.WHATSAPP_EXCLUDES)


def is_curated_folder(name: str) -> bool:
    """Vrai si le dossier n'est PAS un dossier standard (année ou 'MM MOIS')."""
    return not (_ANNEE_RE.match(name) or _MOIS_RE.match(name))


def destination(library: Path, source_file: Path, date_result, mtype: str) -> Path:
    """Calcule le chemin de destination complet du fichier."""
    if date_result.date is None:
        return library / "_A_TRIER" / source_file.name

    racine = library
    if is_whatsapp(source_file):
        racine = racine / "WhatsApp"
    racine = racine / ("Photos" if mtype == "photo" else "Videos")

    annee = f"{date_result.date.year:04d}"
    mois = config.month_folder(date_result.date.month)
    return racine / annee / mois / source_file.name
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python -m pytest tests/test_classify.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediasort/classify.py tests/test_classify.py
git commit -m "feat(classify): calcul du chemin de destination (type, WhatsApp, ANNÉE/MOIS)"
```

---

### Task 8: `noise.py` — détection et nettoyage du bruit

**Files:**
- Create: `mediasort/noise.py`
- Test: `tests/test_noise.py`

**Interfaces:**
- Consumes: `config.NOISE_EXTS`.
- Produces: `noise.is_noise(path: pathlib.Path) -> bool`, `noise.clean_noise(root: pathlib.Path, dry_run: bool) -> list[pathlib.Path]`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_noise.py
import pathlib
from mediasort import noise


def test_is_noise():
    assert noise.is_noise(pathlib.Path("/x/vocal.opus")) is True
    assert noise.is_noise(pathlib.Path("/x/msgstore.db.crypt14")) is True
    assert noise.is_noise(pathlib.Path("/x/.nomedia")) is True
    assert noise.is_noise(pathlib.Path("/x/._IMG_0001.MP4")) is True  # AppleDouble
    assert noise.is_noise(pathlib.Path("/x/IMG_0001.jpg")) is False


def test_clean_noise_dry_run_removes_nothing(tmp_path):
    bruit = tmp_path / "vocal.opus"; bruit.write_bytes(b"x")
    listes = noise.clean_noise(tmp_path, dry_run=True)
    assert bruit in listes
    assert bruit.exists()  # dry-run : rien supprimé


def test_clean_noise_removes_noise(tmp_path):
    bruit = tmp_path / "vocal.opus"; bruit.write_bytes(b"x")
    garde = tmp_path / "photo.jpg"; garde.write_bytes(b"y")
    listes = noise.clean_noise(tmp_path, dry_run=False)
    assert not bruit.exists()
    assert garde.exists()
    assert bruit in listes
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python -m pytest tests/test_noise.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire le module**

```python
# mediasort/noise.py
"""Détection et suppression sûre du bruit résiduel après tri."""

from pathlib import Path

from . import config


def is_noise(path: Path) -> bool:
    """Vrai si le fichier est du bruit connu (jamais un vrai média)."""
    nom = path.name
    if nom.startswith("._"):          # fichiers AppleDouble (macOS)
        return True
    if nom == ".nomedia":
        return True
    return path.suffix.lower() in config.NOISE_EXTS


def clean_noise(root: Path, dry_run: bool) -> list[Path]:
    """Repère (et supprime si dry_run=False) le bruit sous 'root'. Renvoie la liste."""
    trouves: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and is_noise(p):
            trouves.append(p)
            if not dry_run:
                p.unlink()
    return trouves
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python -m pytest tests/test_noise.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediasort/noise.py tests/test_noise.py
git commit -m "feat(noise): détection et nettoyage sûr du bruit"
```

---

### Task 9: `sorter.py` — orchestration du tri

**Files:**
- Create: `mediasort/sorter.py`
- Test: `tests/test_sorter.py`

**Interfaces:**
- Consumes: `classify`, `dates.resolve_date`, `hashing.file_hash`, `catalog.Catalog`.
- Produces:
  - `sorter.Report` (dataclass : `listed:int, sorted:int, duplicates:int, to_triage:int, skipped:int, errors:int`)
  - `sorter.sort_folder(source: pathlib.Path, library: pathlib.Path, catalog, dry_run: bool = True) -> Report`

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_sorter.py
import datetime
import pathlib
from mediasort import sorter, dates
from mediasort.catalog import Catalog


def _force_date(monkeypatch, d):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: d)


def test_sort_places_photo_by_date(tmp_path, monkeypatch):
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.sorted == 1
    assert (lib / "Photos" / "2023" / "05 MAI" / "a.jpg").exists()
    assert not (src / "a.jpg").exists()  # source retirée après copie vérifiée
    cat.close()


def test_sort_dry_run_moves_nothing(tmp_path, monkeypatch):
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=True)

    assert report.sorted == 1  # compté comme "serait rangé"
    assert (src / "a.jpg").exists()  # rien déplacé
    assert not (lib / "Photos").exists()
    cat.close()


def test_sort_skips_duplicate(tmp_path, monkeypatch):
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    (src / "copie.jpg").write_bytes(b"photo-a")  # même contenu
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.sorted == 1
    assert report.duplicates == 1
    cat.close()


def test_sort_unknown_date_goes_to_triage(tmp_path, monkeypatch):
    _force_date(monkeypatch, None)
    monkeypatch.setattr(dates, "date_from_filesystem", lambda p: None)
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "mystere.jpg").write_bytes(b"x")
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.to_triage == 1
    assert (lib / "_A_TRIER" / "mystere.jpg").exists()
    cat.close()
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python -m pytest tests/test_sorter.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire l'orchestration**

```python
# mediasort/sorter.py
"""Orchestration : parcourt une source, range chaque média en toute sûreté."""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import classify
from .dates import resolve_date
from .hashing import file_hash

log = logging.getLogger("mediasort")


@dataclass
class Report:
    """Compteurs du déroulement d'un tri."""
    listed: int = 0
    sorted: int = 0
    duplicates: int = 0
    to_triage: int = 0
    skipped: int = 0
    errors: int = 0


def _chemin_libre(destination: Path) -> Path:
    """Si le nom existe déjà (contenu différent), suffixe _1, _2, ..."""
    if not destination.exists():
        return destination
    tige, suffixe = destination.stem, destination.suffix
    n = 1
    while True:
        candidat = destination.with_name(f"{tige}_{n}{suffixe}")
        if not candidat.exists():
            return candidat
        n += 1


def sort_folder(source: Path, library: Path, catalog, dry_run: bool = True) -> Report:
    """Range tous les médias de 'source' dans 'library'. Renvoie un Report."""
    report = Report()
    for p in sorted(source.rglob("*")):
        if not p.is_file():
            continue
        mtype = classify.media_type(p.suffix)
        if mtype is None:
            continue  # ni photo ni vidéo : ignoré ici (le bruit est traité à part)
        if classify.is_excluded(p):
            report.skipped += 1
            continue
        report.listed += 1
        try:
            empreinte = file_hash(p)
            if catalog.has_hash(empreinte):
                report.duplicates += 1
                log.info("DOUBLON ignoré : %s", p)
                continue

            dr = resolve_date(p)
            dest = classify.destination(library, p, dr, mtype)
            if dr.date is None:
                report.to_triage += 1
            else:
                report.sorted += 1
            log.info("%s -> %s (date: %s)", p.name, dest, dr.source)

            if dry_run:
                continue

            dest = _chemin_libre(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
            # Copie sûre : on vérifie l'empreinte à destination avant de retirer la source.
            if file_hash(dest) != empreinte:
                report.errors += 1
                log.error("Empreinte différente après copie : %s", dest)
                continue
            catalog.add_media(empreinte, p.stat().st_size, str(dest),
                              dr.date.isoformat() if dr.date else None, dr.source)
            p.unlink()
        except OSError as e:
            report.errors += 1
            log.error("Erreur sur %s : %s", p, e)
    return report
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python -m pytest tests/test_sorter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediasort/sorter.py tests/test_sorter.py
git commit -m "feat(sorter): orchestration du tri avec copie sûre et anti-doublon"
```

---

### Task 10: `cli.py` — interface ligne de commande + README

**Files:**
- Create: `mediasort/cli.py`, `mediasort/__main__.py`
- Modify: `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `sorter.sort_folder`, `catalog.Catalog`, `noise.clean_noise`.
- Produces: `cli.main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_cli.py
import datetime
from mediasort import cli, dates
from mediasort.catalog import Catalog


def test_cli_dry_run_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    db = tmp_path / "cat.db"

    code = cli.main(["--source", str(src), "--library", str(lib),
                     "--catalog", str(db), "--dry-run"])

    assert code == 0
    sortie = capsys.readouterr().out
    assert "rangé" in sortie.lower() or "range" in sortie.lower()
    assert (src / "a.jpg").exists()  # dry-run
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire la CLI**

```python
# mediasort/cli.py
"""Interface en ligne de commande du trieur."""

import argparse
import logging
from pathlib import Path

from .catalog import Catalog
from .noise import clean_noise
from .sorter import sort_folder


def main(argv=None) -> int:
    parseur = argparse.ArgumentParser(
        prog="mediasort",
        description="Range des photos/vidéos dans une bibliothèque par date.",
    )
    parseur.add_argument("--source", required=True, type=Path, help="dossier source à trier")
    parseur.add_argument("--library", required=True, type=Path, help="bibliothèque cible")
    parseur.add_argument("--catalog", type=Path, default=Path("catalog.db"),
                         help="fichier du catalogue SQLite")
    parseur.add_argument("--dry-run", action="store_true", help="simulation : ne rien déplacer")
    parseur.add_argument("--seed", action="store_true",
                         help="amorcer le catalogue depuis la bibliothèque existante")
    parseur.add_argument("--clean-noise", action="store_true",
                         help="supprimer le bruit résiduel après tri")
    parseur.add_argument("--verbose", action="store_true", help="journal détaillé")
    args = parseur.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(message)s")

    cat = Catalog(args.catalog)
    try:
        if args.seed:
            n = cat.seed_from_library(args.library)
            print(f"Catalogue amorcé : {n} médias existants indexés.")

        report = sort_folder(args.source, args.library, cat, dry_run=args.dry_run)
        prefixe = "[SIMULATION] " if args.dry_run else ""
        print(f"{prefixe}Bilan : {report.sorted} rangés, {report.duplicates} doublons ignorés, "
              f"{report.to_triage} à trier, {report.skipped} exclus, {report.errors} erreurs.")

        if args.clean_noise:
            supprimes = clean_noise(args.source, dry_run=args.dry_run)
            verbe = "à supprimer" if args.dry_run else "supprimés"
            print(f"{prefixe}Bruit {verbe} : {len(supprimes)} fichiers.")
    finally:
        cat.close()
    return 0
```

```python
# mediasort/__main__.py
"""Permet 'python -m mediasort'."""
import sys
from .cli import main
sys.exit(main())
```

- [ ] **Step 4: Lancer le test et vérifier le succès**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Compléter le README (français)**

Ajouter à `README.md` une section « Trieur de médias (Python) » :

````markdown
## Trieur de médias (Python)

### Mise en place de l'environnement
```bash
sudo apt-get install -y libimage-exiftool-perl ffmpeg python3-venv
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt   # pytest (pour les tests)
```

### Utilisation
```bash
# 1) Amorcer le catalogue depuis la bibliothèque existante (une fois) :
python -m mediasort --library /media/izquierdo/Famille --source /tmp/vide --seed --dry-run

# 2) Simulation du tri d'un dossier (rien n'est déplacé) :
python -m mediasort --source /media/izquierdo/Famille/unsorted \
                    --library /media/izquierdo/Famille --dry-run --verbose

# 3) Tri réel + nettoyage du bruit :
python -m mediasort --source /media/izquierdo/Famille/unsorted \
                    --library /media/izquierdo/Famille --clean-noise
```

### Tests
```bash
. .venv/bin/activate && python -m pytest -v
```
````

- [ ] **Step 6: Lancer toute la suite de tests**

Run: `python -m pytest -v`
Expected: PASS (tous les modules).

- [ ] **Step 7: Commit**

```bash
git add mediasort/cli.py mediasort/__main__.py tests/test_cli.py README.md
git commit -m "feat(cli): interface ligne de commande + doc README"
```

---

## Auto-revue (couverture du spec)

- §4 architecture / modules → Tasks 1-10 (un module = une tâche). ✅
- §5 résolution de date (métadonnées > nom > système > inconnue) → Tasks 2, 3, 4. ✅
- §6 taxonomie (Photos/Videos, WhatsApp, ANNÉE/MOIS, `_A_TRIER`, exclusions) → Task 7. ✅
- §7 catalogue SQLite (anti-doublon, amorçage, synchros) → Task 6. ✅
- §8 nettoyage du bruit sécurisé → Task 8 (+ câblé en Task 10). ✅
- §9 robustesse (dry-run, copie-vérifie-retire, journal, renommage collision) → Task 9. ✅
- §10 CLI (`--source/--library/--dry-run/--seed/--clean-noise/--verbose`) → Task 10. ✅
- §11 plan de test (tests unitaires + fixtures ; test grandeur nature sur `unsorted`) → tests de chaque tâche ; le test réel sur `Famille/unsorted` se fait à l'exécution, après la suite verte. ✅
- §12 environnement (exiftool, ffprobe, venv) → README en Task 10. ✅

**Reste volontairement hors plan** (sous-projets/étapes suivants) : service d'ingestion + mDNS (sous-projet 2), app Android (sous-projet 3), réparation ELEMENTS et sauvegarde de Famille (administration), phases 2-3.

**Note d'exécution :** après la suite de tests verte, lancer le **test grandeur nature** sur `Famille/unsorted` en `--dry-run --verbose`, relire le journal ensemble, puis exécuter réellement.
