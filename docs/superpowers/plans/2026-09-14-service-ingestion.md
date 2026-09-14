# Plan d'implémentation — Service d'ingestion + découverte réseau (sous-projet 2, v1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire `mediaserve`, un service FastAPI sur le NUC qui reçoit les médias poussés par le téléphone (sans doublon), les range via `mediasort`, expose une page web d'admin, et se rend trouvable en mDNS.

**Architecture:** Paquet Python `mediaserve/` (un module = une responsabilité) qui réutilise `mediasort` (Catalog, sort_folder). Serveur FastAPI + uvicorn, lancé par systemd, découvert via Avahi. Anti-doublon par poignée de main d'empreintes réutilisant le catalogue. Développement piloté par les tests (pytest + TestClient FastAPI), commits fréquents.

**Tech Stack:** Python 3, FastAPI, uvicorn, python-multipart, qrcode (SVG) ; `mediasort` (stdlib) ; tests `pytest` + `TestClient`.

**Spec:** `docs/superpowers/specs/2026-09-14-service-ingestion-design.md`

## Global Constraints

- **Documentation et commentaires en français.**
- **Chemins jamais en dur** : tout via `mediaserve/config.py` (surchargeable par variables d'environnement `PORT`, `LIBRARY_DIR`, `CATALOG_DB`, `INCOMING_DIR`, `DEVICES_DB`).
- **Réutiliser `mediasort`** (Catalog, sort_folder, file_hash) — pas de duplication de la logique de tri.
- **Authentification** : `/sync/*` et `/status` exigent `Authorization: Bearer <secret>` (sinon `401`). La surface d'admin locale (`/`, `/pair`, `/devices`, révocation) est **ouverte sur le LAN en v1** (NUC sur réseau de confiance) — durcissement (auth admin / restriction d'accès) tracé en issue.
- **Sécurité upload** : empêcher la traversée de chemin (`..`, chemin absolu) ; revérifier l'empreinte de chaque fichier reçu.
- **Anti-doublon** : `/sync/plan` répond uniquement les empreintes absentes du catalogue (`Catalog.has_hash`).
- **Port** : 8787. **Type de service mDNS** : `_mediaserve._tcp`.
- **Environnement** : dépendances serveur installées par pip (venv sur le NUC ; en local, `pip install --user -r requirements-server.txt`). Les tests n'ont pas besoin des vrais disques (dossiers temporaires + catalogue temporaire).

---

## Structure des fichiers

```
mediasort/sorter.py       # MODIFIÉ : Report enrichi (photos, videos, whatsapp, octets, par_source_date, par_annee_mois)
mediaserve/
  __init__.py
  config.py    # constantes surchargeables par env
  devices.py   # DeviceStore (SQLite) : pair / validate / list / revoke
  pairing.py   # pairing_payload() + qr_svg()
  sessions.py  # new_session / save_upload (anti-traversée) / cleanup
  stats.py     # disk_stats / media_stats / pie_svg
  ingest.py    # sort_session() avec verrou
  web.py       # admin_html()
  app.py       # FastAPI : auth + endpoints + page admin
tests/
  test_report.py test_serve_config.py test_devices.py test_pairing.py
  test_sessions.py test_stats.py test_ingest.py test_app.py
deploy/
  mediaserve.service  avahi-mediaserve.service  Dockerfile  docker-compose.yml
requirements-server.txt
README.md    # complété : reproduction (Linux + Docker)
```

---

### Task 1: Enrichir `mediasort.sorter.Report` (bilan détaillé)

**Files:**
- Modify: `mediasort/sorter.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Produces: `Report` avec champs supplémentaires `photos:int, videos:int, whatsapp:int, bytes_sorted:int, by_source_date:dict, by_year_month:dict` et méthode `to_dict() -> dict`. `sort_folder` les renseigne.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_report.py
import datetime, pathlib
from mediasort import sorter, dates
from mediasort.catalog import Catalog


def test_report_detailed_counters(tmp_path, monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "WhatsApp").mkdir()
    (src / "photo.jpg").write_bytes(b"une photo")
    (src / "film.mp4").write_bytes(b"une video")
    (src / "WhatsApp" / "wa.jpg").write_bytes(b"wa photo")
    cat = Catalog(":memory:")

    r = sorter.sort_folder(src, lib, cat, dry_run=False)
    d = r.to_dict()

    assert d["sorted"] == 3
    assert d["photos"] == 2 and d["videos"] == 1
    assert d["whatsapp"] == 1
    assert d["by_source_date"]["metadata"] == 3
    assert d["by_year_month"]["2023/05 MAI"] == 3
    assert d["bytes_sorted"] > 0
    cat.close()
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_report.py -v`
Expected: FAIL (`to_dict` / nouveaux champs absents).

- [ ] **Step 3: Enrichir `Report` et `sort_folder`**

Dans `mediasort/sorter.py`, remplacer la dataclass `Report` par :

```python
from dataclasses import dataclass, field

@dataclass
class Report:
    """Compteurs du déroulement d'un tri (avec détail)."""
    listed: int = 0
    sorted: int = 0
    duplicates: int = 0
    to_triage: int = 0
    skipped: int = 0
    errors: int = 0
    photos: int = 0
    videos: int = 0
    whatsapp: int = 0
    bytes_sorted: int = 0
    by_source_date: dict = field(default_factory=dict)
    by_year_month: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sorted": self.sorted, "duplicates": self.duplicates,
            "to_triage": self.to_triage, "skipped": self.skipped,
            "errors": self.errors, "photos": self.photos,
            "videos": self.videos, "whatsapp": self.whatsapp,
            "octets_ranges": self.bytes_sorted,
            "par_source_date": self.by_source_date,
            "par_annee_mois": self.by_year_month,
        }
```

Dans `sort_folder`, juste après le calcul de `dest`/`dr` et l'incrément de
`report.sorted`/`report.to_triage`, ajouter le détail (compter sur les fichiers
retenus, y compris en simulation) :

```python
            # --- détail du bilan ---
            if mtype == "photo":
                report.photos += 1
            elif mtype == "video":
                report.videos += 1
            if classify.is_whatsapp(p):
                report.whatsapp += 1
            report.by_source_date[dr.source] = report.by_source_date.get(dr.source, 0) + 1
            if dr.date is not None:
                cle = f"{dr.date.year:04d}/{__import__('mediasort').config.month_folder(dr.date.month)}"
                report.by_year_month[cle] = report.by_year_month.get(cle, 0) + 1
            try:
                report.bytes_sorted += p.stat().st_size
            except OSError:
                pass
```

(Placer ce bloc avant le `if dry_run: continue`, pour compter aussi en simulation.)

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python3 -m pytest tests/test_report.py tests/test_sorter.py -v`
Expected: PASS (le test détaillé + les anciens tests du sorter).

- [ ] **Step 5: Commit**

```bash
git add mediasort/sorter.py tests/test_report.py
git commit -m "feat(sorter): Report enrichi (photos/videos/whatsapp/octets/dates/année-mois)"
```

---

### Task 2: Échafaudage `mediaserve` + `config.py`

**Files:**
- Create: `requirements-server.txt`, `mediaserve/__init__.py`, `mediaserve/config.py`
- Test: `tests/test_serve_config.py`

**Interfaces:**
- Produces: `config.PORT:int`, `config.LIBRARY_DIR:Path`, `config.CATALOG_DB:Path`, `config.INCOMING_DIR:Path`, `config.DEVICES_DB:Path` (tous surchargeables par variable d'environnement).

- [ ] **Step 1: Installer les dépendances serveur**

```bash
cd /home/invisart/dev/phone_camera_import
printf "fastapi\nuvicorn\npython-multipart\nqrcode\nhttpx\n" > requirements-server.txt
python3 -m pip install --user -r requirements-server.txt
mkdir -p mediaserve
: > mediaserve/__init__.py
```

- [ ] **Step 2: Écrire le test qui échoue**

```python
# tests/test_serve_config.py
import importlib
from pathlib import Path


def test_config_defaults(monkeypatch):
    for v in ("PORT", "LIBRARY_DIR", "CATALOG_DB", "INCOMING_DIR", "DEVICES_DB"):
        monkeypatch.delenv(v, raising=False)
    cfg = importlib.reload(importlib.import_module("mediaserve.config"))
    assert cfg.PORT == 8787
    assert isinstance(cfg.LIBRARY_DIR, Path)


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("LIBRARY_DIR", "/tmp/lib")
    cfg = importlib.reload(importlib.import_module("mediaserve.config"))
    assert cfg.PORT == 9999
    assert str(cfg.LIBRARY_DIR) == "/tmp/lib"
```

- [ ] **Step 3: Lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_serve_config.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Écrire `config.py`**

```python
# mediaserve/config.py
"""Configuration du service (surchargeable par variables d'environnement)."""

import os
from pathlib import Path

PORT: int = int(os.environ.get("PORT", "8787"))
LIBRARY_DIR: Path = Path(os.environ.get("LIBRARY_DIR", "/media/izquierdo/Famille"))
CATALOG_DB: Path = Path(os.environ.get("CATALOG_DB", str(Path.home() / "mediasort_catalog.db")))
INCOMING_DIR: Path = Path(os.environ.get("INCOMING_DIR", str(LIBRARY_DIR / "incoming")))
DEVICES_DB: Path = Path(os.environ.get("DEVICES_DB", str(Path.home() / "mediaserve_devices.db")))
SERVICE_TYPE: str = "_mediaserve._tcp"
```

- [ ] **Step 5: Lancer le test et vérifier le succès**

Run: `python3 -m pytest tests/test_serve_config.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add requirements-server.txt mediaserve/__init__.py mediaserve/config.py tests/test_serve_config.py
git commit -m "feat(mediaserve): échafaudage + config surchargeable par env"
```

---

### Task 3: `devices.py` — jetons d'appareils

**Files:**
- Create: `mediaserve/devices.py`
- Test: `tests/test_devices.py`

**Interfaces:**
- Produces: `DeviceStore(db_path)` avec `pair(label) -> (device_id, secret_clair)`, `validate(secret) -> device_id | None`, `list() -> list[dict]`, `revoke(device_id) -> bool`, `close()`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_devices.py
from mediaserve.devices import DeviceStore


def test_pair_validate_revoke():
    st = DeviceStore(":memory:")
    dev_id, secret = st.pair("Pixel de Ken")
    assert st.validate(secret) == dev_id
    assert st.validate("mauvais") is None
    liste = st.list()
    assert len(liste) == 1 and liste[0]["label"] == "Pixel de Ken"
    assert st.revoke(dev_id) is True
    assert st.validate(secret) is None
    st.close()


def test_secret_not_stored_in_clear():
    st = DeviceStore(":memory:")
    _, secret = st.pair("x")
    rows = st._cx.execute("SELECT secret_hash FROM devices").fetchall()
    assert secret not in [r[0] for r in rows]  # jamais le secret en clair
    st.close()
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_devices.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire le module**

```python
# mediaserve/devices.py
"""Stockage et validation des jetons d'appareils appairés (SQLite)."""

import hashlib
import secrets
import sqlite3
import uuid
from datetime import datetime


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class DeviceStore:
    """Un appareil appairé = un secret (stocké haché) + un label."""

    def __init__(self, db_path) -> None:
        self._cx = sqlite3.connect(str(db_path))
        self._cx.execute(
            "CREATE TABLE IF NOT EXISTS devices ("
            " id TEXT PRIMARY KEY, label TEXT, secret_hash TEXT UNIQUE, paired_at TEXT)"
        )
        self._cx.commit()

    def pair(self, label: str) -> tuple[str, str]:
        """Crée un appareil, renvoie (id, secret en clair) — le secret n'est montré qu'ici."""
        dev_id = uuid.uuid4().hex
        secret = secrets.token_urlsafe(32)
        self._cx.execute(
            "INSERT INTO devices (id, label, secret_hash, paired_at) VALUES (?,?,?,?)",
            (dev_id, label, _hash(secret), datetime.now().isoformat(timespec="seconds")),
        )
        self._cx.commit()
        return dev_id, secret

    def validate(self, secret: str) -> "str | None":
        cur = self._cx.execute("SELECT id FROM devices WHERE secret_hash=?", (_hash(secret),))
        row = cur.fetchone()
        return row[0] if row else None

    def list(self) -> list:
        cur = self._cx.execute("SELECT id, label, paired_at FROM devices ORDER BY paired_at")
        return [{"id": i, "label": l, "paired_at": p} for (i, l, p) in cur.fetchall()]

    def revoke(self, device_id: str) -> bool:
        cur = self._cx.execute("DELETE FROM devices WHERE id=?", (device_id,))
        self._cx.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._cx.close()
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python3 -m pytest tests/test_devices.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediaserve/devices.py tests/test_devices.py
git commit -m "feat(mediaserve): DeviceStore (appairage/validation/révocation de jetons)"
```

---

### Task 4: `pairing.py` — QR d'appairage

**Files:**
- Create: `mediaserve/pairing.py`
- Test: `tests/test_pairing.py`

**Interfaces:**
- Produces: `pairing_payload(url, token, cert_sha256=None) -> dict`, `qr_svg(data: str) -> str`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_pairing.py
from mediaserve import pairing


def test_pairing_payload():
    p = pairing.pairing_payload("http://nuc.local:8787", "secret123")
    assert p == {"url": "http://nuc.local:8787", "token": "secret123", "cert_sha256": None}


def test_qr_svg_is_svg():
    svg = pairing.qr_svg("bonjour")
    assert "<svg" in svg and "</svg>" in svg
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_pairing.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire le module**

```python
# mediaserve/pairing.py
"""Charge utile d'appairage + génération du QR code (SVG, sans Pillow)."""

import qrcode
import qrcode.image.svg


def pairing_payload(url: str, token: str, cert_sha256=None) -> dict:
    """Données encodées dans le QR : où joindre le NUC + secret (+ empreinte certif future)."""
    return {"url": url, "token": token, "cert_sha256": cert_sha256}


def qr_svg(data: str) -> str:
    """Rend un QR code au format SVG (chaîne)."""
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgImage)
    return img.to_string(encoding="unicode")
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python3 -m pytest tests/test_pairing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediaserve/pairing.py tests/test_pairing.py
git commit -m "feat(mediaserve): charge utile d'appairage + QR SVG"
```

---

### Task 5: `sessions.py` — sessions d'upload (anti-traversée)

**Files:**
- Create: `mediaserve/sessions.py`
- Test: `tests/test_sessions.py`

**Interfaces:**
- Produces: `new_session() -> str`, `save_upload(base: Path, session: str, rel_path: str, content: bytes) -> Path`, `cleanup(base: Path, session: str) -> None`. `save_upload` refuse la traversée de chemin.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_sessions.py
import pytest
from mediaserve import sessions


def test_save_upload_writes_under_session(tmp_path):
    s = sessions.new_session()
    p = sessions.save_upload(tmp_path, s, "Pictures/WhatsApp/a.jpg", b"data")
    assert p.read_bytes() == b"data"
    assert (tmp_path / s / "Pictures" / "WhatsApp" / "a.jpg") == p


def test_save_upload_rejects_traversal(tmp_path):
    s = sessions.new_session()
    with pytest.raises(ValueError):
        sessions.save_upload(tmp_path, s, "../../etc/passwd", b"x")
    with pytest.raises(ValueError):
        sessions.save_upload(tmp_path, s, "/abs/chemin.jpg", b"x")


def test_cleanup_removes_session(tmp_path):
    s = sessions.new_session()
    sessions.save_upload(tmp_path, s, "a.jpg", b"x")
    sessions.cleanup(tmp_path, s)
    assert not (tmp_path / s).exists()
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_sessions.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire le module**

```python
# mediaserve/sessions.py
"""Sessions de synchro : réception des fichiers dans incoming/<session>/."""

import shutil
import uuid
from pathlib import Path


def new_session() -> str:
    """Identifiant de session (hex)."""
    return uuid.uuid4().hex


def _chemin_sur(base: Path, session: str, rel_path: str) -> Path:
    """Résout le chemin de destination en refusant toute sortie du dossier de session."""
    racine = (base / session).resolve()
    cible = (racine / rel_path).resolve()
    if not str(cible).startswith(str(racine) + "/") and cible != racine:
        raise ValueError(f"chemin non autorisé : {rel_path}")
    return cible


def save_upload(base: Path, session: str, rel_path: str, content: bytes) -> Path:
    """Écrit le fichier reçu sous incoming/<session>/<rel_path> (anti-traversée)."""
    if rel_path.startswith("/") or ".." in Path(rel_path).parts:
        raise ValueError(f"chemin non autorisé : {rel_path}")
    cible = _chemin_sur(base, session, rel_path)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(content)
    return cible


def cleanup(base: Path, session: str) -> None:
    """Supprime le dossier de session."""
    shutil.rmtree(base / session, ignore_errors=True)
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python3 -m pytest tests/test_sessions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediaserve/sessions.py tests/test_sessions.py
git commit -m "feat(mediaserve): sessions d'upload avec protection anti-traversée"
```

---

### Task 6: `stats.py` — stats disque + médias + camembert SVG

**Files:**
- Create: `mediaserve/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `mediasort.classify.media_type`.
- Produces: `disk_stats(path: Path) -> dict`, `media_stats(catalog_db: Path) -> dict`, `pie_svg(used: int, free: int) -> str`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_stats.py
from pathlib import Path
from mediaserve import stats
from mediasort.catalog import Catalog


def test_disk_stats(tmp_path):
    d = stats.disk_stats(tmp_path)
    assert d["total"] > 0 and d["libre"] >= 0
    assert 0 <= d["pourcentage_utilise"] <= 100


def test_media_stats(tmp_path):
    db = tmp_path / "cat.db"
    cat = Catalog(str(db))
    cat.add_media("h1", 10, "/lib/Photos/2023/a.jpg", "2023-05-26", "metadata")
    cat.add_media("h2", 20, "/lib/Videos/2023/b.mp4", "2023-05-26", "metadata")
    cat.close()
    m = stats.media_stats(db)
    assert m["photos"] == 1 and m["videos"] == 1


def test_pie_svg(tmp_path):
    svg = stats.pie_svg(used=700, free=300)
    assert "<svg" in svg and "</svg>" in svg
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_stats.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire le module**

```python
# mediaserve/stats.py
"""Statistiques disque et médias + rendu d'un camembert SVG (côté serveur)."""

import math
import shutil
import sqlite3
from pathlib import Path

from mediasort.classify import media_type


def disk_stats(path: Path) -> dict:
    """Espace du disque contenant 'path'."""
    u = shutil.disk_usage(str(path))
    pct = round(100 * u.used / u.total) if u.total else 0
    return {"total": u.total, "utilise": u.used, "libre": u.free, "pourcentage_utilise": pct}


def media_stats(catalog_db: Path) -> dict:
    """Compte photos/vidéos au catalogue (déduit du type d'extension du chemin)."""
    photos = videos = 0
    cx = sqlite3.connect(str(catalog_db))
    try:
        for (chemin,) in cx.execute("SELECT chemin FROM medias"):
            t = media_type(Path(chemin).suffix)
            if t == "photo":
                photos += 1
            elif t == "video":
                videos += 1
    finally:
        cx.close()
    return {"photos": photos, "videos": videos}


def _arc(cx, cy, r, a0, a1):
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    grand = 1 if (a1 - a0) > math.pi else 0
    return f"M{cx},{cy} L{x0:.1f},{y0:.1f} A{r},{r} 0 {grand} 1 {x1:.1f},{y1:.1f} Z"


def pie_svg(used: int, free: int) -> str:
    """Camembert SVG utilisé (foncé) / libre (clair)."""
    total = used + free or 1
    a0 = -math.pi / 2
    a_used = a0 + 2 * math.pi * used / total
    p_used = _arc(60, 60, 55, a0, a_used)
    p_free = _arc(60, 60, 55, a_used, a0 + 2 * math.pi)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120">'
        f'<path d="{p_used}" fill="#3b6ea5"/><path d="{p_free}" fill="#d7e3f0"/></svg>'
    )
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python3 -m pytest tests/test_stats.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediaserve/stats.py tests/test_stats.py
git commit -m "feat(mediaserve): stats disque/médias + camembert SVG"
```

---

### Task 7: `ingest.py` — tri d'une session (avec verrou)

**Files:**
- Create: `mediaserve/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `mediasort.sorter.sort_folder`, `mediasort.catalog.Catalog`.
- Produces: `sort_session(session_dir: Path, library: Path, catalog) -> dict` (le bilan détaillé, `Report.to_dict()`), sérialisé par un verrou global.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_ingest.py
import datetime
from mediaserve import ingest
from mediasort import dates
from mediasort.catalog import Catalog


def test_sort_session_returns_bilan(tmp_path, monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    sess = tmp_path / "sess"; (sess / "Pictures").mkdir(parents=True)
    (sess / "Pictures" / "a.jpg").write_bytes(b"photo")
    lib = tmp_path / "lib"; lib.mkdir()
    cat = Catalog(":memory:")

    bilan = ingest.sort_session(sess, lib, cat)

    assert bilan["sorted"] == 1 and bilan["photos"] == 1
    assert (lib / "Photos" / "2023" / "05 MAI" / "a.jpg").exists()
    cat.close()
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_ingest.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire le module**

```python
# mediaserve/ingest.py
"""Intégration du trieur : range une session reçue, un tri à la fois."""

import threading
from pathlib import Path

from mediasort.sorter import sort_folder

_verrou = threading.Lock()


def sort_session(session_dir: Path, library: Path, catalog) -> dict:
    """Range les fichiers de la session dans la bibliothèque. Renvoie le bilan détaillé."""
    with _verrou:  # un seul tri à la fois
        report = sort_folder(session_dir, library, catalog, dry_run=False)
    return report.to_dict()
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python3 -m pytest tests/test_ingest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediaserve/ingest.py tests/test_ingest.py
git commit -m "feat(mediaserve): tri d'une session avec verrou, renvoie le bilan"
```

---

### Task 8: `web.py` — page HTML d'admin

**Files:**
- Create: `mediaserve/web.py`
- Test: `tests/test_app.py` (section web ; le fichier est créé ici, complété en Task 9-11)

**Interfaces:**
- Consumes: `stats.pie_svg`.
- Produces: `admin_html(devices: list, disk: dict, media: dict) -> str`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_app.py
from mediaserve import web


def test_admin_html_contains_devices_and_pie():
    html = web.admin_html(
        devices=[{"id": "abc", "label": "Pixel", "paired_at": "2026-09-14"}],
        disk={"total": 1000, "utilise": 700, "libre": 300, "pourcentage_utilise": 70},
        media={"photos": 40000, "videos": 4669},
    )
    assert "Pixel" in html            # l'appareil est listé
    assert "abc" in html              # son id (pour le bouton révoquer)
    assert "<svg" in html             # le camembert
    assert "/pair" in html            # lien vers l'appairage
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_app.py::test_admin_html_contains_devices_and_pie -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Écrire le module**

```python
# mediaserve/web.py
"""Page HTML d'administration (appairage, appareils, stats disque)."""

from . import stats


def _go(n: int) -> str:
    for unite in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024:
            return f"{n:.0f} {unite}"
        n /= 1024
    return f"{n:.0f} Po"


def admin_html(devices: list, disk: dict, media: dict) -> str:
    """Rend la page d'admin : QR (lien), liste d'appareils + révocation, camembert."""
    lignes = "".join(
        f'<li>{d["label"]} <small>({d["paired_at"]})</small> '
        f'<button onclick="revoke(\'{d["id"]}\')">Révoquer</button></li>'
        for d in devices
    ) or "<li>Aucun appareil appairé</li>"
    pie = stats.pie_svg(disk["utilise"], disk["libre"])
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>mediaserve — admin</title></head><body>
<h1>mediaserve</h1>
<p><a href="/pair">➕ Appairer un nouveau téléphone (QR)</a></p>
<h2>Appareils appairés</h2><ul>{lignes}</ul>
<h2>Disque</h2>{pie}
<p>{_go(disk["utilise"])} utilisés / {_go(disk["total"])} — libre : {_go(disk["libre"])} ({100-disk["pourcentage_utilise"]}%)</p>
<h2>Médias</h2><p>{media["photos"]} photos, {media["videos"]} vidéos</p>
<script>
function revoke(id){{fetch('/devices/'+id+'/revoke',{{method:'POST'}}).then(()=>location.reload());}}
</script></body></html>"""
```

- [ ] **Step 4: Lancer le test et vérifier le succès**

Run: `python3 -m pytest tests/test_app.py::test_admin_html_contains_devices_and_pie -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediaserve/web.py tests/test_app.py
git commit -m "feat(mediaserve): page HTML d'admin (appareils + camembert)"
```

---

### Task 9: `app.py` — auth + `/status` + `/devices` + révocation

**Files:**
- Create: `mediaserve/app.py`
- Test: `tests/test_app.py` (compléter)

**Interfaces:**
- Consumes: `config`, `DeviceStore`, `stats`.
- Produces: `app` (FastAPI). Dépendance d'auth `require_device`. Route `GET /status` (**auth**) ; `GET /devices` et `POST /devices/{id}/revoke` (**surface d'admin locale, sans auth** — cf. Global Constraints).

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_app.py  (ajouter)
import importlib
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path))
    monkeypatch.setenv("CATALOG_DB", str(tmp_path / "cat.db"))
    monkeypatch.setenv("INCOMING_DIR", str(tmp_path / "incoming"))
    monkeypatch.setenv("DEVICES_DB", str(tmp_path / "dev.db"))
    import mediaserve.config as c; importlib.reload(c)
    import mediaserve.app as a; importlib.reload(a)
    return a, TestClient(a.app)


def test_status_requires_auth(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    assert client.get("/status").status_code == 401


def test_status_with_token(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices.pair("test")
    r = client.get("/status", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_list_and_revoke_device(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices.pair("Pixel")
    # /devices et la révocation sont sur la surface d'admin locale (sans jeton)
    assert any(d["id"] == dev_id for d in client.get("/devices").json())
    assert client.post(f"/devices/{dev_id}/revoke").status_code == 200
    # le jeton de l'appareil révoqué ne marche plus sur la surface authentifiée
    assert client.get("/status", headers={"Authorization": f"Bearer {secret}"}).status_code == 401
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_app.py -v`
Expected: FAIL (`ModuleNotFoundError` mediaserve.app).

- [ ] **Step 3: Écrire l'app (auth + status + devices)**

```python
# mediaserve/app.py
"""Application FastAPI du service d'ingestion."""

from fastapi import Depends, FastAPI, Header, HTTPException

from . import config, stats, web
from .devices import DeviceStore

app = FastAPI(title="mediaserve")
devices = DeviceStore(config.DEVICES_DB)


def require_device(authorization: str = Header(default="")) -> str:
    """Dépendance d'auth : exige 'Authorization: Bearer <secret>' valide."""
    prefixe = "Bearer "
    secret = authorization[len(prefixe):] if authorization.startswith(prefixe) else ""
    dev_id = devices.validate(secret) if secret else None
    if not dev_id:
        raise HTTPException(status_code=401, detail="jeton invalide")
    return dev_id


@app.get("/status")
def status(_: str = Depends(require_device)) -> dict:
    d = stats.disk_stats(config.LIBRARY_DIR)
    m = stats.media_stats(config.CATALOG_DB) if config.CATALOG_DB.exists() else {"photos": 0, "videos": 0}
    return {"ok": True, "library": str(config.LIBRARY_DIR),
            "catalog_count": m["photos"] + m["videos"], "disque": d, "medias": m}


@app.get("/devices")   # surface d'admin locale (sans auth, cf. Global Constraints)
def list_devices() -> list:
    return devices.list()


@app.post("/devices/{device_id}/revoke")   # surface d'admin locale (sans auth)
def revoke_device(device_id: str) -> dict:
    return {"revoked": devices.revoke(device_id)}
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python3 -m pytest tests/test_app.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediaserve/app.py tests/test_app.py
git commit -m "feat(mediaserve): app FastAPI — auth, /status, /devices, révocation"
```

---

### Task 10: `app.py` — flux de synchro `/sync/plan` + `/upload` + `/commit`

**Files:**
- Modify: `mediaserve/app.py`
- Test: `tests/test_app.py` (compléter)

**Interfaces:**
- Consumes: `Catalog`, `sessions`, `ingest`, `file_hash`.
- Produces: `POST /sync/plan`, `POST /sync/upload`, `POST /sync/commit` (voir §4 du spec).

- [ ] **Step 1: Écrire le test qui échoue (synchro de bout en bout)**

```python
# tests/test_app.py  (ajouter)
import datetime, hashlib, io


def test_sync_flow_dedup_and_commit(tmp_path, monkeypatch):
    import mediasort.dates as d; monkeypatch.setattr(d, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices.pair("Pixel"); h = {"Authorization": f"Bearer {secret}"}

    contenu = b"une vraie photo"
    empreinte = hashlib.sha256(contenu).hexdigest()

    # 1) plan : le NUC ne l'a pas -> il le réclame
    plan = client.post("/sync/plan", headers=h, json={"files": [
        {"path": "Pictures/a.jpg", "size": len(contenu), "hash": empreinte}]})
    assert plan.status_code == 200
    session = plan.json()["session"]
    assert empreinte in plan.json()["needed"]

    # 2) upload
    up = client.post("/sync/upload", headers=h,
                     data={"session": session, "path": "Pictures/a.jpg"},
                     files={"file": ("a.jpg", io.BytesIO(contenu), "image/jpeg")})
    assert up.status_code == 200 and up.json()["hash"] == empreinte

    # 3) commit -> bilan détaillé
    commit = client.post("/sync/commit", headers=h, json={"session": session})
    assert commit.status_code == 200
    assert commit.json()["sorted"] == 1 and commit.json()["photos"] == 1
    assert (tmp_path / "Photos" / "2023" / "05 MAI" / "a.jpg").exists()

    # 4) re-plan du même fichier -> plus réclamé (déjà au catalogue)
    plan2 = client.post("/sync/plan", headers=h, json={"files": [
        {"path": "Pictures/a.jpg", "size": len(contenu), "hash": empreinte}]})
    assert empreinte not in plan2.json()["needed"]
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_app.py::test_sync_flow_dedup_and_commit -v`
Expected: FAIL (routes `/sync/*` absentes).

- [ ] **Step 3: Ajouter les routes de synchro dans `app.py`**

```python
# mediaserve/app.py  (ajouter les imports en tête)
from fastapi import Form, UploadFile, File
from pydantic import BaseModel

from mediasort.catalog import Catalog
from mediasort.hashing import file_hash
from . import sessions, ingest


class FileSig(BaseModel):
    path: str
    size: int
    hash: str


class PlanRequest(BaseModel):
    files: list[FileSig]


class CommitRequest(BaseModel):
    session: str


@app.post("/sync/plan")
def sync_plan(req: PlanRequest, _: str = Depends(require_device)) -> dict:
    cat = Catalog(config.CATALOG_DB)
    try:
        manquants = [f.hash for f in req.files if not cat.has_hash(f.hash)]
    finally:
        cat.close()
    return {"session": sessions.new_session(), "needed": manquants}


@app.post("/sync/upload")
async def sync_upload(session: str = Form(...), path: str = Form(...),
                      file: UploadFile = File(...), _: str = Depends(require_device)) -> dict:
    contenu = await file.read()
    try:
        dest = sessions.save_upload(config.INCOMING_DIR, session, path, contenu)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "hash": file_hash(dest)}


@app.post("/sync/commit")
def sync_commit(req: CommitRequest, _: str = Depends(require_device)) -> dict:
    session_dir = config.INCOMING_DIR / req.session
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="session inconnue")
    cat = Catalog(config.CATALOG_DB)
    try:
        bilan = ingest.sort_session(session_dir, config.LIBRARY_DIR, cat)
    finally:
        cat.close()
    sessions.cleanup(config.INCOMING_DIR, req.session)
    return bilan
```

- [ ] **Step 4: Lancer les tests et vérifier le succès**

Run: `python3 -m pytest tests/test_app.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mediaserve/app.py tests/test_app.py
git commit -m "feat(mediaserve): flux de synchro plan/upload/commit"
```

---

### Task 11: `app.py` — `/pair` + page d'admin `/`

**Files:**
- Modify: `mediaserve/app.py`
- Test: `tests/test_app.py` (compléter)

**Interfaces:**
- Consumes: `pairing`, `web`.
- Produces: `GET /pair` (HTML + QR, crée un appareil), `GET /` (page d'admin). Ces deux routes sont **publiques** (pas d'auth : elles servent à s'appairer / voir l'état localement).

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_app.py  (ajouter)
def test_pair_page_creates_device_and_qr(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    avant = len(a.devices.list())
    r = client.get("/pair")
    assert r.status_code == 200 and "<svg" in r.text
    assert len(a.devices.list()) == avant + 1  # un appareil créé


def test_admin_page_renders(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200 and "mediaserve" in r.text
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_app.py -v`
Expected: FAIL (routes `/pair`, `/` absentes).

- [ ] **Step 3: Ajouter les routes dans `app.py`**

```python
# mediaserve/app.py  (ajouter les imports)
import json
from fastapi.responses import HTMLResponse
from . import pairing


@app.get("/pair", response_class=HTMLResponse)
def pair() -> str:
    _, secret = devices.pair("Nouveau téléphone")
    url = f"http://nuc.local:{config.PORT}"
    charge = json.dumps(pairing.pairing_payload(url, secret))
    svg = pairing.qr_svg(charge)
    return (f'<!doctype html><meta charset="utf-8"><title>Appairage</title>'
            f'<h1>Scanne ce QR avec l\'app</h1>{svg}'
            f'<p>Ou saisis manuellement : <code>{url}</code></p>')


@app.get("/", response_class=HTMLResponse)
def admin() -> str:
    d = stats.disk_stats(config.LIBRARY_DIR)
    m = stats.media_stats(config.CATALOG_DB) if config.CATALOG_DB.exists() else {"photos": 0, "videos": 0}
    return web.admin_html(devices.list(), d, m)
```

- [ ] **Step 4: Lancer toute la suite**

Run: `python3 -m pytest -v`
Expected: PASS (tous les modules).

- [ ] **Step 5: Commit**

```bash
git add mediaserve/app.py tests/test_app.py
git commit -m "feat(mediaserve): pages /pair (QR) et / (admin)"
```

---

### Task 12: Déploiement (systemd, Avahi, Docker) + README

**Files:**
- Create: `deploy/mediaserve.service`, `deploy/avahi-mediaserve.service`, `deploy/Dockerfile`, `deploy/docker-compose.yml`
- Modify: `README.md`

**Interfaces:** aucun code testable (fichiers de conf + doc). Vérification = démarrage manuel.

- [ ] **Step 1: Unité systemd**

```ini
# deploy/mediaserve.service
[Unit]
Description=mediaserve (ingestion médias)
After=network-online.target media-izquierdo-Famille.mount
Wants=network-online.target

[Service]
User=izquierdo
WorkingDirectory=/home/izquierdo/phone_camera_import
ExecStart=/home/izquierdo/.venv-server/bin/uvicorn mediaserve.app:app --host 0.0.0.0 --port 8787
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Service Avahi (mDNS)**

```xml
<!-- deploy/avahi-mediaserve.service -->
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">mediaserve sur %h</name>
  <service>
    <type>_mediaserve._tcp</type>
    <port>8787</port>
  </service>
</service-group>
```

- [ ] **Step 3: Dockerfile**

```dockerfile
# deploy/Dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libimage-exiftool-perl ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
COPY mediasort/ mediasort/
COPY mediaserve/ mediaserve/
ENV LIBRARY_DIR=/data/library CATALOG_DB=/data/catalog.db INCOMING_DIR=/data/incoming DEVICES_DB=/data/devices.db
EXPOSE 8787
CMD ["uvicorn", "mediaserve.app:app", "--host", "0.0.0.0", "--port", "8787"]
```

- [ ] **Step 4: docker-compose**

```yaml
# deploy/docker-compose.yml
services:
  mediaserve:
    build: { context: .., dockerfile: deploy/Dockerfile }
    network_mode: host          # nécessaire pour le mDNS/Avahi
    volumes:
      - /media/izquierdo/Famille:/data/library
      - mediaserve-data:/data
    restart: unless-stopped
volumes:
  mediaserve-data:
```

- [ ] **Step 5: Vérifier que l'app démarre (fumée)**

Run: `python3 -c "import mediaserve.app; print('import OK')"`
Expected: `import OK` (pas d'erreur d'import).

- [ ] **Step 6: Compléter le README (français)**

Ajouter une section « Service d'ingestion (mediaserve) » : mise en place venv +
dépendances, lancement uvicorn, pose du service systemd + Avahi, et la
**reproduction Docker** (`docker compose -f deploy/docker-compose.yml up -d`,
volume médias, réseau hôte pour le mDNS, variables `LIBRARY_DIR`/`CATALOG_DB`/…).

- [ ] **Step 7: Commit**

```bash
git add deploy/ README.md
git commit -m "feat(mediaserve): déploiement systemd/Avahi/Docker + README de reproduction"
```

---

## Auto-revue (couverture du spec)

- §2 décisions → réparties sur les tâches. ✅
- §3 modules (`config/devices/pairing/sessions/stats/web/app/ingest`) → Tasks 2-11. ✅
- §4.1 `/pair` (QR) → Task 11 ; §4.2 `/sync/plan` (handshake) → Task 10 ; §4.3 `/sync/upload` (intégrité + anti-traversée) → Tasks 5, 10 ; §4.4 `/sync/commit` (bilan détaillé) → Tasks 1, 7, 10 ; §4.5 `/status` → Task 9 ; §4.6 `/devices` + révocation → Task 9 ; §4.7 page admin (camembert) → Tasks 6, 8, 11. ✅
- §5 auth Bearer + révocation web → Tasks 3, 9. ✅
- §6 mDNS Avahi → Task 12. ✅
- §7 intégration trieur (incoming, chemins préservés, verrou) → Tasks 5, 7, 10. ✅
- §8 déploiement (systemd, point de vigilance montage, Docker, README) → Task 12. ✅
- §9 robustesse (reprise via plan, intégrité, verrou) → Tasks 5, 7, 10. ✅
- §10 tests (TestClient) → Tasks 9-11. ✅

**Note d'exécution :** après la suite verte en local, déployer sur le NUC (venv
serveur + service), ouvrir `http://nuc.local:8787/` pour vérifier la page d'admin
et `http://nuc.local:8787/pair` pour le QR, avant d'attaquer le sous-projet 3.

**Point de vigilance (Task 12) :** valider si le service systemd doit être
`--user` (lingering) ou système avec dépendance sur le point de montage des
disques `/media/izquierdo` (voir spec §8).
