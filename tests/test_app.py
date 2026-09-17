import datetime, hashlib, importlib, io
from fastapi.testclient import TestClient
from phototheque import web


def test_admin_html_contains_devices_and_figures():
    html = web.admin_html(
        devices=[{"id": "abc", "label": "Pixel", "paired_at": "2026-09-14"}],
        disk={"total": 1000, "utilise": 700, "libre": 300, "pourcentage_utilise": 70},
        media={"photos": 40000, "videos": 4669},
    )
    assert "Pixel" in html and "abc" in html and "/pair" in html
    assert "40 000" in html and "4 669" in html   # chiffres lisibles, espaces fines


def test_admin_meter_reflects_disk_usage():
    """La jauge remplit exactement le pourcentage occupé."""
    html = web.admin_html(
        devices=[],
        disk={"total": 1000, "utilise": 430, "libre": 570, "pourcentage_utilise": 43},
        media={"photos": 1, "videos": 1},
    )
    assert "width:43%" in html.replace(" ", "")


def test_admin_warns_in_words_not_only_in_colour():
    """Disque presque plein : un mot, pas seulement une couleur.

    Règle d'accessibilité : une couleur d'état ne porte jamais l'information
    seule (daltonisme, impression, contraste forcé).
    """
    plein = web.admin_html(
        devices=[],
        disk={"total": 1000, "utilise": 940, "libre": 60, "pourcentage_utilise": 94},
        media={"photos": 1, "videos": 1})
    assert "presque plein" in plein.lower()

    normal = web.admin_html(
        devices=[],
        disk={"total": 1000, "utilise": 100, "libre": 900, "pourcentage_utilise": 10},
        media={"photos": 1, "videos": 1})
    assert "presque plein" not in normal.lower()


def test_pages_support_dark_mode():
    """Les deux pages suivent le thème clair/sombre du système."""
    html = web.admin_html(
        devices=[], disk={"total": 1, "utilise": 0, "libre": 1, "pourcentage_utilise": 0},
        media={"photos": 0, "videos": 0})
    assert "prefers-color-scheme: dark" in html
    assert "prefers-color-scheme: dark" in web.pair_html("<svg></svg>", "http://x:8787")


def test_pair_html_keeps_the_qr_on_a_light_background():
    """Le QR est noir sur fond transparent : en thème sombre il disparaîtrait."""
    html = web.pair_html("<svg id=\"qr\"></svg>", "http://essai.local:8787")
    assert "<svg id=\"qr\">" in html
    assert "http://essai.local:8787" in html
    assert "#fff" in html.lower() or "#ffffff" in html.lower()


def test_admin_html_marks_pending_pairings():
    """La page distingue un téléphone en service d'un QR jamais scanné."""
    disque = {"total": 1000, "utilise": 700, "libre": 300, "pourcentage_utilise": 70}
    media = {"photos": 1, "videos": 1}

    html = web.admin_html(
        devices=[{"id": "a", "label": "Pixel", "paired_at": "2026-09-17",
                  "en_attente": False},
                 {"id": "b", "label": "Nouveau téléphone", "paired_at": "2026-09-17",
                  "en_attente": True}],
        disk=disque, media=media)
    assert "en attente" in html.lower()

    confirmes = web.admin_html(
        devices=[{"id": "a", "label": "Pixel", "paired_at": "2026-09-17",
                  "en_attente": False}],
        disk=disque, media=media)
    assert "en attente" not in confirmes.lower()


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path))
    monkeypatch.setenv("CATALOG_DB", str(tmp_path / "cat.db"))
    monkeypatch.setenv("INCOMING_DIR", str(tmp_path / "incoming"))
    monkeypatch.setenv("DEVICES_DB", str(tmp_path / "dev.db"))
    import phototheque.config as c; importlib.reload(c)
    import phototheque.app as a; importlib.reload(a)
    return a, TestClient(a.app)


def test_status_requires_auth(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    assert client.get("/status").status_code == 401


def test_status_with_token(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("test")
    r = client.get("/status", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_list_and_revoke_device(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    assert any(d["id"] == dev_id for d in client.get("/devices").json())
    assert client.post(f"/devices/{dev_id}/revoke").status_code == 200
    assert client.get("/status", headers={"Authorization": f"Bearer {secret}"}).status_code == 401


def test_sync_flow_dedup_and_commit(tmp_path, monkeypatch):
    import mediasort.dates as d
    monkeypatch.setattr(d, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel"); h = {"Authorization": f"Bearer {secret}"}
    contenu = b"une vraie photo"; empreinte = hashlib.sha256(contenu).hexdigest()
    plan = client.post("/sync/plan", headers=h, json={"files": [
        {"path": "Pictures/a.jpg", "size": len(contenu), "hash": empreinte}]})
    assert plan.status_code == 200
    session = plan.json()["session"]
    assert empreinte in plan.json()["needed"]
    up = client.post("/sync/upload", headers=h,
                     data={"session": session, "path": "Pictures/a.jpg"},
                     files={"file": ("a.jpg", io.BytesIO(contenu), "image/jpeg")})
    assert up.status_code == 200 and up.json()["hash"] == empreinte
    commit = client.post("/sync/commit", headers=h, json={"session": session})
    assert commit.status_code == 200
    assert commit.json()["sorted"] == 1 and commit.json()["photos"] == 1
    assert (tmp_path / "Photos" / "2023" / "05 MAI" / "a.jpg").exists()
    plan2 = client.post("/sync/plan", headers=h, json={"files": [
        {"path": "Pictures/a.jpg", "size": len(contenu), "hash": empreinte}]})
    assert empreinte not in plan2.json()["needed"]


def test_pair_page_creates_device_and_qr(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    avant = len(a.devices().list())
    r = client.get("/pair")
    assert r.status_code == 200 and "<svg" in r.text
    assert len(a.devices().list()) == avant + 1


def test_admin_page_renders(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 200 and "phototheque" in r.text


def test_importing_app_does_not_create_the_devices_db(tmp_path, monkeypatch):
    """Importer le module ne doit RIEN écrire dans le dossier personnel.

    Régression du 17/09/2026 : DeviceStore était instancié au chargement du
    module, donc lancer les tests sur le NUC créait ~/phototheque_devices.db
    vide, ce qui a fait sauter la reprise des appairages au déploiement.
    """
    base = tmp_path / "dev.db"
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path))
    monkeypatch.setenv("CATALOG_DB", str(tmp_path / "cat.db"))
    monkeypatch.setenv("INCOMING_DIR", str(tmp_path / "incoming"))
    monkeypatch.setenv("DEVICES_DB", str(base))
    import phototheque.config as c; importlib.reload(c)
    import phototheque.app as a; importlib.reload(a)

    assert not base.exists(), "l'import du module a créé la base des appareils"

    # ...mais la base est bien ouverte à la première utilisation réelle.
    a.devices().pair("Pixel")
    assert base.exists()


def test_pair_page_purges_stale_pairings(tmp_path, monkeypatch):
    """Afficher /pair ne doit pas accumuler des jetons valables à l'infini.

    Chaque visite crée un secret ; sans ménage, chaque page d'appairage
    ouverte par curiosité laissait une clé d'accès permanente.
    """
    from datetime import datetime, timedelta
    a, client = _client(tmp_path, monkeypatch)

    client.get("/pair")
    ancien = a.devices().list()[0]["id"]
    vieux = (datetime.now() - timedelta(minutes=11)).isoformat(timespec="seconds")
    a.devices()._cx.execute("UPDATE devices SET paired_at=? WHERE id=?", (vieux, ancien))
    a.devices()._cx.commit()

    client.get("/pair")

    restants = a.devices().list()
    assert len(restants) == 1, restants
    assert restants[0]["id"] != ancien


def test_pair_page_publishes_a_reachable_url(tmp_path, monkeypatch):
    """Le QR et le texte affiché portent l'URL réelle du serveur."""
    monkeypatch.setenv("PUBLIC_URL", "http://essai-hote.local:8787")
    a, client = _client(tmp_path, monkeypatch)
    r = client.get("/pair")
    assert "essai-hote.local:8787" in r.text
    assert "nuc.local" not in r.text


def test_pair_page_reuses_the_same_qr_while_valid(tmp_path, monkeypatch):
    """Recharger /pair ne doit PAS créer un second identifiant.

    Un GET ne doit rien modifier. Avant ce correctif, chaque appel — sonde de
    supervision, préchargement du navigateur, vérification du script
    d'installation — fabriquait une clé d'accès.
    """
    a, client = _client(tmp_path, monkeypatch)
    premier = client.get("/pair")
    second = client.get("/pair")

    assert premier.status_code == second.status_code == 200
    assert premier.text == second.text, "un nouveau QR a été généré"
    assert len(a.devices().list()) == 1


def test_pair_page_issues_a_new_qr_once_the_previous_is_used(tmp_path, monkeypatch):
    """Une fois le téléphone appairé, la page propose un appairage neuf."""
    a, client = _client(tmp_path, monkeypatch)
    client.get("/pair")
    en_cours = a.devices().list()[0]["id"]
    # Le téléphone scanne et se connecte : l'appairage est confirmé.
    _, secret = a._appairage_en_cours
    assert a.devices().validate(secret) == en_cours

    client.get("/pair")

    liste = a.devices().list()
    assert len(liste) == 2
    assert sum(1 for d in liste if d["en_attente"]) == 1


def test_admin_shows_readable_dates():
    """Les dates sont lisibles, pas au format machine."""
    html = web.admin_html(
        devices=[{"id": "a", "label": "Pixel", "paired_at": "2026-09-15T21:04:11",
                  "en_attente": False}],
        disk={"total": 1, "utilise": 0, "libre": 1, "pourcentage_utilise": 0},
        media={"photos": 0, "videos": 0})
    assert "15 sept. 2026 à 21:04" in html
    assert "2026-09-15T21:04:11" not in html


def test_admin_tolerates_an_unreadable_date():
    """Une date inattendue s'affiche telle quelle plutôt que de casser la page."""
    html = web.admin_html(
        devices=[{"id": "a", "label": "Pixel", "paired_at": "bizarre", "en_attente": False}],
        disk={"total": 1, "utilise": 0, "libre": 1, "pourcentage_utilise": 0},
        media={"photos": 0, "videos": 0})
    assert "bizarre" in html
