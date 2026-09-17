import datetime, hashlib, importlib, io
import pytest
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
    assert "prefers-color-scheme: dark" in web.pair_html("<svg></svg>", "http://x:8787", "2026-09-17")


def test_pair_html_keeps_the_qr_on_a_light_background():
    """Le QR est noir sur fond transparent : en thème sombre il disparaîtrait."""
    html = web.pair_html("<svg id=\"qr\"></svg>", "http://essai.local:8787", "2026-09-17")
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
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    assert any(d["id"] == dev_id for d in client.get("/devices", headers=entetes).json())
    assert client.post(f"/devices/{dev_id}/revoke", headers=entetes).status_code == 200
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
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    avant = len(a.devices().list())
    r = client.get("/pair", headers=entetes)
    assert r.status_code == 200 and "<svg" in r.text
    assert len(a.devices().list()) == avant + 1


def test_admin_page_renders(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    r = client.get("/", headers=entetes)
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
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)

    client.get("/pair", headers=entetes)
    ancien = a.devices().list()[0]["id"]
    vieux = (datetime.now() - timedelta(minutes=11)).isoformat(timespec="seconds")
    a.devices()._cx.execute("UPDATE devices SET paired_at=? WHERE id=?", (vieux, ancien))
    a.devices()._cx.commit()

    client.get("/pair", headers=entetes)

    restants = a.devices().list()
    assert len(restants) == 1, restants
    assert restants[0]["id"] != ancien


def test_pair_page_publishes_a_reachable_url(tmp_path, monkeypatch):
    """Le QR et le texte affiché portent l'URL réelle du serveur."""
    monkeypatch.setenv("PUBLIC_URL", "http://essai-hote.local:8787")
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    r = client.get("/pair", headers=entetes)
    assert "essai-hote.local:8787" in r.text
    assert "nuc.local" not in r.text


def test_pair_page_reuses_the_same_qr_while_valid(tmp_path, monkeypatch):
    """Recharger /pair ne doit PAS créer un second identifiant.

    Un GET ne doit rien modifier. Avant ce correctif, chaque appel — sonde de
    supervision, préchargement du navigateur, vérification du script
    d'installation — fabriquait une clé d'accès.
    """
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    premier = client.get("/pair", headers=entetes)
    second = client.get("/pair", headers=entetes)

    assert premier.status_code == second.status_code == 200
    assert premier.text == second.text, "un nouveau QR a été généré"
    assert len(a.devices().list()) == 1


def test_pair_page_issues_a_new_qr_once_the_previous_is_used(tmp_path, monkeypatch):
    """Une fois le téléphone appairé, la page propose un appairage neuf."""
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/pair", headers=entetes)
    en_cours = a.devices().list()[0]["id"]
    # Le téléphone scanne et se connecte : l'appairage est confirmé.
    _, secret = a._appairage_en_cours
    assert a.devices().validate(secret) == en_cours

    client.get("/pair", headers=entetes)

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


def test_pair_qr_transporte_l_empreinte_du_certificat(tmp_path, monkeypatch):
    """Le QR porte l'empreinte que l'application épinglera (issue #3)."""
    import json
    import subprocess
    from phototheque import tls

    cert = tmp_path / "cert.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-subj", "/CN=essai.local", "-keyout", str(tmp_path / "key.pem"),
         "-out", str(cert)],
        check=True, capture_output=True)
    monkeypatch.setenv("CERT_FILE", str(cert))
    entetes = _avec_admin(tmp_path, monkeypatch)

    a, client = _client(tmp_path, monkeypatch)
    client.get("/pair", headers=entetes)     # crée l'appairage en cours
    charge = json.loads(a.charge_appairage())

    assert charge["cert_sha256"] == tls.empreinte_certificat(cert)


def test_pair_sans_certificat_ne_casse_pas(tmp_path, monkeypatch):
    """Service lancé à la main en HTTP : pas de certificat, pas d'empreinte."""
    import json
    monkeypatch.setenv("CERT_FILE", str(tmp_path / "absent.pem"))
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/pair", headers=entetes)     # crée l'appairage en cours

    charge = json.loads(a.charge_appairage())

    assert charge["cert_sha256"] is None
    assert client.get("/pair", headers=entetes).status_code == 200


ADRESSES_ADMIN = ["/", "/pair", "/devices"]


def _avec_admin(tmp_path, monkeypatch, mot_de_passe="secret-admin"):
    """Installe un mot de passe admin et renvoie l'en-tête correspondant."""
    import base64
    from phototheque import adminauth
    fichier = tmp_path / "admin"
    fichier.write_text(adminauth.empreinte(mot_de_passe, iterations=1000))
    monkeypatch.setenv("ADMIN_FILE", str(fichier))
    jeton = base64.b64encode(f"admin:{mot_de_passe}".encode()).decode()
    return {"Authorization": f"Basic {jeton}"}


@pytest.mark.parametrize("adresse", ADRESSES_ADMIN)
def test_les_adresses_d_admin_exigent_un_mot_de_passe(adresse, tmp_path, monkeypatch):
    """Un test par adresse : ajouter une route non protégée casse la suite."""
    _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    r = client.get(adresse)
    assert r.status_code == 401, adresse
    assert "Basic" in r.headers.get("WWW-Authenticate", ""), adresse


def test_revocation_exige_un_mot_de_passe(tmp_path, monkeypatch):
    _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    assert client.post("/devices/peu-importe/revoke").status_code == 401


@pytest.mark.parametrize("adresse", ADRESSES_ADMIN)
def test_le_bon_mot_de_passe_ouvre_l_admin(adresse, tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    assert client.get(adresse, headers=entetes).status_code == 200, adresse


def test_un_mauvais_mot_de_passe_est_refuse(tmp_path, monkeypatch):
    import base64
    _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    faux = base64.b64encode(b"admin:pas-le-bon").decode()
    r = client.get("/", headers={"Authorization": f"Basic {faux}"})
    assert r.status_code == 401


def test_sans_fichier_de_mot_de_passe_l_admin_est_fermee(tmp_path, monkeypatch):
    """Pas encore installé : on refuse plutôt que d'ouvrir en grand."""
    monkeypatch.setenv("ADMIN_FILE", str(tmp_path / "jamais-cree"))
    a, client = _client(tmp_path, monkeypatch)
    assert client.get("/").status_code == 401


def test_un_fichier_admin_corrompu_ferme_l_admin_sans_erreur_500(tmp_path, monkeypatch):
    """Fichier d'identifiants illisible : refus propre, pas d'erreur serveur."""
    fichier = tmp_path / "admin"
    fichier.write_bytes(b"\xff\xfe pas de l'UTF-8")
    monkeypatch.setenv("ADMIN_FILE", str(fichier))
    a, client = _client(tmp_path, monkeypatch)
    assert client.get("/").status_code == 401


def test_la_page_d_appairage_propose_une_date(tmp_path, monkeypatch):
    """Par défaut aujourd'hui : on ne remonte pas tout l'historique."""
    import datetime
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    r = client.get("/pair", headers=entetes)
    assert 'name="depuis"' in r.text
    assert datetime.date.today().isoformat() in r.text


def test_poster_une_date_l_enregistre_sur_l_appairage(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/pair", headers=entetes)
    dev_id = a.devices().list()[0]["id"]

    r = client.post("/pair", headers=entetes, data={"depuis": "2020-01-01"})

    assert r.status_code == 200
    assert a.devices().get_horizon_initial(dev_id) == "2020-01-01"
    assert "2020-01-01" in r.text


def test_une_date_invalide_est_refusee(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/pair", headers=entetes)
    assert client.post("/pair", headers=entetes,
                       data={"depuis": "hier"}).status_code == 400


def test_poster_une_date_sur_un_appairage_perime_l_applique_au_nouveau(tmp_path, monkeypatch):
    """Page laissée ouverte trop longtemps : la date suit le QR réellement affiché.

    Sans cela, POST /pair écrivait dans le vide sur un appairage déjà purgé et
    réaffichait un QR pointant vers un appareil inexistant — en silence.
    """
    from datetime import datetime, timedelta
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/pair", headers=entetes)
    perime = a.devices().list()[0]["id"]
    vieux = (datetime.now() - timedelta(minutes=11)).isoformat(timespec="seconds")
    a.devices()._cx.execute("UPDATE devices SET paired_at=? WHERE id=?", (vieux, perime))
    a.devices()._cx.commit()

    r = client.post("/pair", headers=entetes, data={"depuis": "2020-01-01"})

    assert r.status_code == 200
    restants = a.devices().list()
    assert len(restants) == 1
    assert restants[0]["id"] != perime       # l'appairage périmé a été purgé
    assert a.devices().get_horizon_initial(restants[0]["id"]) == "2020-01-01"


def test_horizon_exige_un_jeton_d_appareil(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    assert client.get("/sync/horizon").status_code == 401


def test_horizon_renvoie_la_date_d_appairage_au_premier_appel(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    a.devices().set_horizon_initial(dev_id, "2026-09-17")

    r = client.get("/sync/horizon", headers={"Authorization": f"Bearer {secret}"})

    assert r.status_code == 200
    assert r.json() == {"depuis": "2026-09-17", "dossiers": {}}


def test_horizon_renvoie_les_dossiers_deja_synchronises(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    a.devices().set_horizon(dev_id, "DCIM/Camera", 1726574400.0)

    r = client.get("/sync/horizon", headers={"Authorization": f"Bearer {secret}"})
    assert r.json()["dossiers"] == {"DCIM/Camera": 1726574400.0}


def test_horizon_renvoie_null_pour_un_appareil_migre(tmp_path, monkeypatch):
    """Appareil appairé avant l'introduction du réglage : aucune limite.

    Élément du contrat que l'application code en dur : elle doit recevoir
    null, pas une absence de clé ni une chaîne vide.

    L'appareil est fabriqué ici dans l'ancien schéma, puis repris par la
    migration : c'est le SEUL cas où l'horizon initial vaut encore NULL. Un
    appairage neuf, lui, part de la date du jour (voir le test suivant).
    """
    import sqlite3
    from phototheque.devices import _hash
    base = tmp_path / "dev.db"
    cx = sqlite3.connect(str(base))
    cx.execute("CREATE TABLE devices (id TEXT PRIMARY KEY, label TEXT,"
               " secret_hash TEXT UNIQUE, paired_at TEXT, confirmed_at TEXT)")
    cx.execute("INSERT INTO devices VALUES ('vieux','Pixel',?,"
               "'2026-01-01T10:00:00','2026-01-01T10:00:00')",
               (_hash("secret-historique"),))
    cx.commit(); cx.close()

    a, client = _client(tmp_path, monkeypatch)

    r = client.get("/sync/horizon",
                   headers={"Authorization": "Bearer secret-historique"})

    assert r.status_code == 200
    assert r.json()["depuis"] is None


def test_un_telephone_appaire_sans_toucher_au_formulaire_part_d_aujourd_hui(
        tmp_path, monkeypatch):
    """Le scénario courant : on affiche le QR, le téléphone scanne, c'est tout.

    Reproduit : un simple GET /pair suivi d'un scan donnait
    {"depuis": null, "dossiers": {}}, c'est-à-dire « aucune limite » — le
    téléphone remontait tout son historique alors que la page affichait bien
    « aujourd'hui ». Cette valeur n'était enregistrée que si l'administrateur
    cliquait sur « Enregistrer ».
    """
    import datetime
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/pair", headers=entetes)          # on n'envoie PAS le formulaire
    _, secret = a._appairage_en_cours

    r = client.get("/sync/horizon", headers={"Authorization": f"Bearer {secret}"})

    assert r.status_code == 200
    assert r.json() == {"depuis": datetime.date.today().isoformat(), "dossiers": {}}


def test_le_commit_enregistre_les_horizons(tmp_path, monkeypatch):
    import datetime, hashlib, io
    import mediasort.dates as d
    monkeypatch.setattr(d, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    contenu = b"une photo"; empreinte = hashlib.sha256(contenu).hexdigest()
    session = client.post("/sync/plan", headers=h, json={"files": [
        {"path": "DCIM/Camera/a.jpg", "size": len(contenu), "hash": empreinte}]
    }).json()["session"]
    client.post("/sync/upload", headers=h,
                data={"session": session, "path": "DCIM/Camera/a.jpg"},
                files={"file": ("a.jpg", io.BytesIO(contenu), "image/jpeg")})

    r = client.post("/sync/commit", headers=h, json={
        "session": session, "horizons": {"DCIM/Camera": 1726574400.0}})

    assert r.status_code == 200
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1726574400.0}


def test_un_commit_qui_echoue_ne_fait_pas_avancer_l_horizon(tmp_path, monkeypatch):
    """Session inconnue : l'horizon ne bouge pas, la prochaine synchro reprend.

    « inexistante » n'a pas la forme d'un identifiant de session : le commit
    est refusé avant tout. À ne pas confondre avec une session vide, qui a une
    forme valable et se termine normalement (test plus bas).
    """
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")

    r = client.post("/sync/commit",
                    headers={"Authorization": f"Bearer {secret}"},
                    json={"session": "inexistante",
                          "horizons": {"DCIM/Camera": 1726574400.0}})

    assert r.status_code == 404
    assert a.devices().get_horizons(dev_id) == {}


def test_le_commit_sans_horizons_reste_accepte(tmp_path, monkeypatch):
    """Champ facultatif : un client qui ne l'envoie pas fonctionne toujours.

    La session est volontairement hors norme : on vérifie que le refus vient
    de l'identifiant, pas du format de la requête.
    """
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel")
    r = client.post("/sync/commit", headers={"Authorization": f"Bearer {secret}"},
                    json={"session": "inexistante"})
    assert r.status_code == 404      # refusée pour la session, pas pour le format


def test_un_tri_qui_leve_une_exception_ne_fait_pas_avancer_l_horizon(tmp_path, monkeypatch):
    """Le scénario central : la synchro casse en route, l'horizon ne bouge pas."""
    import io
    from phototheque import ingest
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": [
        {"path": "DCIM/Camera/a.jpg", "size": 3, "hash": "abc"}]}).json()["session"]
    client.post("/sync/upload", headers=h,
                data={"session": session, "path": "DCIM/Camera/a.jpg"},
                files={"file": ("a.jpg", io.BytesIO(b"abc"), "image/jpeg")})

    def tri_qui_casse(*a, **kw):
        raise OSError("disque plein")

    monkeypatch.setattr(ingest, "sort_session", tri_qui_casse)
    with pytest.raises(OSError):
        client.post("/sync/commit", headers=h, json={
            "session": session, "horizons": {"DCIM/Camera": 1726574400.0}})

    assert a.devices().get_horizons(dev_id) == {}


def test_un_tri_avec_des_erreurs_ne_fait_pas_avancer_l_horizon(tmp_path, monkeypatch):
    """Tri « réussi » mais un fichier a échoué : il a été supprimé avec la session.

    Faire avancer l'horizon reviendrait à dire au téléphone « bien reçu »
    pour un média qui n'existe plus nulle part. On préfère qu'il repropose.
    """
    import io
    from phototheque import ingest
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": [
        {"path": "DCIM/Camera/a.jpg", "size": 3, "hash": "abc"}]}).json()["session"]
    client.post("/sync/upload", headers=h,
                data={"session": session, "path": "DCIM/Camera/a.jpg"},
                files={"file": ("a.jpg", io.BytesIO(b"abc"), "image/jpeg")})

    monkeypatch.setattr(ingest, "sort_session", lambda *a, **kw: {
        "sorted": 0, "duplicates": 0, "to_triage": 0, "skipped": 0, "errors": 1,
        "photos": 0, "videos": 0, "whatsapp": 0, "octets_ranges": 0,
        "par_source_date": {}, "par_annee_mois": {}})

    r = client.post("/sync/commit", headers=h, json={
        "session": session, "horizons": {"DCIM/Camera": 1726574400.0}})

    assert r.status_code == 200
    assert a.devices().get_horizons(dev_id) == {}


def _session_ouverte(client, entetes):
    """Ouvre une session de synchro et renvoie son identifiant."""
    return client.post("/sync/plan", headers=entetes,
                       json={"files": []}).json()["session"]


def test_une_extension_que_le_trieur_ignore_est_refusee_a_l_upload(tmp_path, monkeypatch):
    """Perte définitive et silencieuse, reproduite avec un .webm.

    Le serveur acceptait n'importe quelle extension et répondait « bien
    reçu ». Le trieur, lui, ignore les extensions qu'il ne connaît pas : le
    fichier n'était ni rangé ni même compté, le nettoyage de fin de session le
    supprimait, et le bilan sans erreur faisait avancer l'horizon. Le
    téléphone ne le reproposait donc jamais : média perdu, sans un mot.

    Refuser à l'upload garde le fichier SUR LE TÉLÉPHONE et laisse l'horizon
    avancer pour tout le reste.
    """
    import io
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = _session_ouverte(client, h)

    r = client.post("/sync/upload", headers=h,
                    data={"session": session, "path": "Movies/film.webm"},
                    files={"file": ("film.webm", io.BytesIO(b"video"), "video/webm")})

    assert r.status_code == 400
    assert ".webm" in r.json()["detail"]
    dossier = tmp_path / "incoming" / session
    assert not dossier.exists(), "le fichier refusé a quand même été écrit sur le NUC"


def test_un_jpg_passe_toujours_a_l_upload(tmp_path, monkeypatch):
    """Le cas normal ne doit pas être cassé par le refus des extensions."""
    import hashlib, io
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = _session_ouverte(client, h)
    contenu = b"une vraie photo"

    r = client.post("/sync/upload", headers=h,
                    data={"session": session, "path": "DCIM/Camera/a.jpg"},
                    files={"file": ("a.jpg", io.BytesIO(contenu), "image/jpeg")})

    assert r.status_code == 200
    assert r.json()["hash"] == hashlib.sha256(contenu).hexdigest()


def test_une_extension_refusee_n_empeche_pas_la_session_de_se_terminer(tmp_path, monkeypatch):
    """Enchaînement complet : un .webm refusé, un .jpg accepté, puis commit.

    Le refus ne doit pas bloquer la synchro : les médias que le serveur sait
    ranger sont rangés et l'horizon avance normalement pour eux.
    """
    import datetime, io
    import mediasort.dates as d
    monkeypatch.setattr(d, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = _session_ouverte(client, h)

    refuse = client.post("/sync/upload", headers=h,
                         data={"session": session, "path": "Movies/film.webm"},
                         files={"file": ("film.webm", io.BytesIO(b"v"), "video/webm")})
    accepte = client.post("/sync/upload", headers=h,
                          data={"session": session, "path": "DCIM/Camera/a.jpg"},
                          files={"file": ("a.jpg", io.BytesIO(b"photo"), "image/jpeg")})
    commit = client.post("/sync/commit", headers=h, json={
        "session": session, "horizons": {"DCIM/Camera": 1726574400.0}})

    assert refuse.status_code == 400 and accepte.status_code == 200
    assert commit.status_code == 200
    assert commit.json()["errors"] == 0 and commit.json()["sorted"] == 1
    assert (tmp_path / "Photos" / "2023" / "05 MAI" / "a.jpg").exists()
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1726574400.0}


def test_un_commit_sans_aucun_fichier_envoye_fait_avancer_l_horizon(tmp_path, monkeypatch):
    """Le régime permanent : la bibliothèque est à jour, il n'y a rien à envoyer.

    Reproduit : `sessions.new_session()` ne crée aucun dossier — il n'apparaît
    qu'au premier upload. Un plan qui ne réclame aucun fichier suivi d'un
    commit tombait donc sur « session inconnue » (404) et l'horizon n'était
    jamais enregistré. Le téléphone rescannait indéfiniment la même fenêtre.

    Une session sans dossier n'est pas une session inconnue : c'est une
    session vide, cas parfaitement normal, traité comme un tri à zéro fichier.
    """
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    r = client.post("/sync/commit", headers=h, json={
        "session": session, "horizons": {"DCIM/Camera": 1726574400.0}})

    assert r.status_code == 200
    bilan = r.json()
    assert bilan["sorted"] == 0 and bilan["errors"] == 0 and bilan["duplicates"] == 0
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1726574400.0}


def test_un_identifiant_de_session_invente_reste_refuse(tmp_path, monkeypatch):
    """Accepter une session vide ne doit pas ouvrir la porte à n'importe quoi.

    Seule la forme produite par `sessions.new_session()` est acceptée : 32
    caractères hexadécimaux. Tout le reste — nom fantaisiste, chemin remontant
    vers un dossier voisin — est refusé avant d'atteindre le disque.
    """
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}

    for invente in ("inexistante", "../..", "", "ZZZ" * 10):
        r = client.post("/sync/commit", headers=h, json={
            "session": invente, "horizons": {"DCIM/Camera": 1726574400.0}})
        assert r.status_code == 404, invente
    assert a.devices().get_horizons(dev_id) == {}


def test_une_session_vide_puis_une_synchro_normale(tmp_path, monkeypatch):
    """C2 et I2 ensemble : un .webm refusé laisse une session sans aucun
    fichier, et cette session doit pouvoir se terminer normalement — sinon
    refuser une extension bloquerait l'horizon du dossier concerné."""
    import io
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    refuse = client.post("/sync/upload", headers=h,
                         data={"session": session, "path": "Movies/film.webm"},
                         files={"file": ("film.webm", io.BytesIO(b"v"), "video/webm")})
    commit = client.post("/sync/commit", headers=h, json={
        "session": session, "horizons": {"Movies": 1726574400.0}})

    assert refuse.status_code == 400
    assert commit.status_code == 200
    assert a.devices().get_horizons(dev_id) == {"Movies": 1726574400.0}
