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
    # Sans cette ligne, config.APK_FILE resterait ~/.local/share/phototheque :
    # le résultat des tests dépendrait de ce qui traîne dans le dossier
    # personnel de celui qui les lance.
    monkeypatch.setenv("APK_FILE", str(tmp_path / "app.apk"))
    # Sans cette ligne, config.JOURNAL_DB resterait ~/phototheque_journal.db :
    # les tests écriraient dans le dossier personnel de qui les lance. Posée
    # SANS lire l'environnement : un `JOURNAL_DB` exporté dans le shell (sur
    # le NUC, par exemple) ne doit jamais faire écrire les tests dans la vraie
    # base. Un test qui veut un autre chemin le pose APRÈS l'appel (voir le
    # test du journal en panne).
    monkeypatch.setenv("JOURNAL_DB", str(tmp_path / "journal.db"))
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


ADRESSES_ADMIN = ["/", "/pair", "/devices", "/apk",
                  "/historique", "/historique/recherche?q=a", "/historique/x",
                  "/evenements"]


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
    # /apk ne sert pas une page mais un fichier : sans dépôt il répond
    # légitimement 404. On en dépose donc un, pour que ce test mesure bien ce
    # qu'il prétend mesurer — l'authentification — et pas l'absence d'APK.
    if adresse == "/apk":
        (tmp_path / "app.apk").write_bytes(b"PK\x03\x04")
    # /historique/x cible une synchro précise : sans elle, la route répond
    # légitimement 404 (identifiant inconnu). On la crée pour que ce test
    # mesure l'authentification, pas l'existence de la synchro.
    if adresse == "/historique/x":
        a.journal().enregistrer_commit("x", "sess-x", "tel", "Pixel", None, {}, None)
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


def test_la_page_d_appairage_ne_propose_plus_de_date(tmp_path, monkeypatch):
    """Constat C5 de la recette du lot 2 (24/09) : le champ date sous le QR.

    Depuis le lot 2, la date de début se règle sur le téléphone et y prime
    toujours (Orchestrateur.kt). Le champ de /pair ne servait donc plus qu'à
    semer le doute : deux endroits pour régler la même chose, dont un sans
    effet. Il est retiré ; le QR et l'adresse de secours restent.
    """
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    r = client.get("/pair", headers=entetes)
    assert r.status_code == 200
    assert 'name="depuis"' not in r.text
    assert 'type="date"' not in r.text
    assert "<svg" in r.text                 # le QR, lui, est toujours là


def test_poster_une_date_sur_pair_n_est_plus_possible(tmp_path, monkeypatch):
    """La route qui servait le champ disparaît avec lui.

    L'horizon par défaut reste posé par le serveur à l'appairage
    (Devices.pair) : c'est la valeur que lit un téléphone sans date de début.
    """
    import datetime
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/pair", headers=entetes)
    dev_id = a.devices().list()[0]["id"]

    r = client.post("/pair", headers=entetes, data={"depuis": "2020-01-01"})

    assert r.status_code == 405
    assert a.devices().get_horizon_initial(dev_id) == datetime.date.today().isoformat()


# --- pages d'historique et d'événements (tâche 6, issue #30) ----------------


def test_un_nom_de_fichier_hostile_est_echappe(tmp_path, monkeypatch):
    """Point d'attention 4 : le nom vient du téléphone, jamais fait confiance."""
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    a.journal().ajouter_mouvement("sess0", {
        "origine": "DCIM/<script>alert(1)</script>.jpg", "taille": 1,
        "empreinte": "e", "issue": "range", "destination": "/b/x.jpg", "detail": None})
    a.journal().enregistrer_commit("s1", "sess0", "tel", "Pixel", None, {}, None)
    for adresse in ["/historique/s1", "/historique/recherche?q=script"]:
        texte = client.get(adresse, headers=entetes).text
        assert "<script>alert" not in texte and "&lt;script&gt;" in texte


def test_l_historique_montre_les_synchros_et_l_admin_y_mene(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    a.journal().enregistrer_commit("s1", "sess0", "tel", "Pixel", "192.168.1.18",
                                   {"sorted": 4}, None)
    assert "Pixel" in client.get("/historique", headers=entetes).text
    assert 'href="/historique"' in client.get("/", headers=entetes).text
    assert client.get("/historique/inconnue", headers=entetes).status_code == 404


def test_l_historique_signale_les_synchros_en_echec_par_un_mot(tmp_path, monkeypatch):
    """Règle d'accessibilité : la couleur d'état ne suffit jamais seule.

    « erreur » seul ne suffit pas à distinguer les deux mots (« sans erreur »
    le contient aussi) : on vérifie le mot exact de chaque état, et que la
    classe CSS qui porte la couleur diffère bien entre les deux lignes.
    """
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    a.journal().enregistrer_commit("ok", "sess-ok", "tel", "Pixel", None,
                                   {"sorted": 1}, None)
    a.journal().enregistrer_commit("ko", "sess-ko", "tel", "Pixel", None,
                                   {"errors": 1}, None)
    texte = client.get("/historique", headers=entetes).text
    assert "en erreur" in texte
    assert "sans erreur" in texte
    assert 'etiquette critical' in texte
    assert 'etiquette ok' in texte


def test_la_page_d_une_synchro_montre_ses_mouvements(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    a.journal().ajouter_mouvement("sess0", {
        "origine": "DCIM/Camera/a.jpg", "taille": 10, "empreinte": "e",
        "issue": "range", "destination": "Photos/2026/09 SEPT/a.jpg", "detail": None})
    a.journal().enregistrer_commit("s1", "sess0", "tel", "Pixel", None, {"sorted": 1}, None)
    texte = client.get("/historique/s1", headers=entetes).text
    assert "DCIM/Camera/a.jpg" in texte
    assert "Photos/2026/09 SEPT/a.jpg" in texte


def test_un_refus_a_l_envoi_se_lit_comme_tel(tmp_path, monkeypatch):
    """M1 : « refusé à l'envoi » (le serveur n'a jamais écrit le fichier)
    ne se confond pas avec « refusé » (reçu, puis ignoré par le trieur)."""
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    a.journal().noter_refus("sess0", "Movies/film.webm", "extension non prise en charge")
    a.journal().enregistrer_commit("s1", "sess0", "tel", "Pixel", None, {}, None)
    texte = client.get("/historique/s1", headers=entetes).text
    assert "refusé à l&#x27;envoi" in texte or "refusé à l'envoi" in texte


def test_la_recherche_vide_n_interroge_pas_le_journal(tmp_path, monkeypatch):
    """`Journal.rechercher("")` ramènerait toute la table : à éviter."""
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    a.journal().ajouter_mouvement("sess0", {
        "origine": "DCIM/Camera/a.jpg", "taille": 10, "empreinte": "e",
        "issue": "range", "destination": "Photos/2026/09 SEPT/a.jpg", "detail": None})
    a.journal().enregistrer_commit("s1", "sess0", "tel", "Pixel", None, {"sorted": 1}, None)

    for adresse in ["/historique/recherche", "/historique/recherche?q=", "/historique/recherche?q=  "]:
        texte = client.get(adresse, headers=entetes).text
        assert "DCIM/Camera/a.jpg" not in texte


def test_la_recherche_trouve_un_mouvement(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    a.journal().ajouter_mouvement("sess0", {
        "origine": "DCIM/Camera/a.jpg", "taille": 10, "empreinte": "e",
        "issue": "range", "destination": "Photos/2026/09 SEPT/a.jpg", "detail": None})
    a.journal().enregistrer_commit("s1", "sess0", "tel", "Pixel", None, {"sorted": 1}, None)
    texte = client.get("/historique/recherche?q=Camera", headers=entetes).text
    assert "DCIM/Camera/a.jpg" in texte


def test_les_evenements_s_affichent(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    a.journal().evenement("appairage", appareil="abc123", adresse="192.168.1.18")
    texte = client.get("/evenements", headers=entetes).text
    assert "appairage" in texte.lower()
    assert "abc123" in texte
    assert "192.168.1.18" in texte


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
    """Tri « réussi » mais un fichier a échoué : l'horizon ne bouge pas.

    Faire avancer l'horizon reviendrait à dire au téléphone « bien reçu » pour
    un média que la bibliothèque n'a pas ; il ne le proposerait plus jamais.
    Depuis l'issue #16 le fichier n'est plus détruit mais mis en quarantaine —
    ça ne change rien ici : l'horizon doit rester immobile dans les deux cas.
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

    # On part du bilan REEL et on n'y change que `errors` : un dictionnaire
    # recopie a la main derive des que Report gagne une cle — c'est ce qui est
    # arrive avec `echecs`, ajoute pour l'issue #16.
    faux_bilan = dict(ingest.bilan_vide(), errors=1)
    monkeypatch.setattr(ingest, "sort_session", lambda *a, **kw: faux_bilan)

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


# --- le journal (issue #30, tâche 3) ----------------------------------------


def test_un_commit_sans_identifiant_de_synchro_fait_une_ligne(tmp_path, monkeypatch):
    """Spec §8.2 : un téléphone qui n'envoie pas `synchro` reste journalisé."""
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    r = client.post("/sync/commit", headers=h, json={"session": session})

    assert r.status_code == 200
    lignes = a.journal().synchros()
    assert len(lignes) == 1 and lignes[0]["appareil"] == dev_id


def test_deux_commits_de_la_meme_synchro_font_une_ligne(tmp_path, monkeypatch):
    """Deux paquets (lot 1 bis) d'une même grosse sauvegarde ne comptent qu'une fois."""
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session1 = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]
    session2 = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    r1 = client.post("/sync/commit", headers=h,
                     json={"session": session1, "synchro": "abc123"})
    r2 = client.post("/sync/commit", headers=h,
                     json={"session": session2, "synchro": "abc123"})

    assert r1.status_code == 200 and r2.status_code == 200
    assert len(a.journal().synchros()) == 1
    assert a.journal().synchros()[0]["paquets"] == 2


def test_la_reponse_du_commit_ne_contient_pas_les_mouvements(tmp_path, monkeypatch):
    """L'app lit la réponse comme un dictionnaire de nombres."""
    import datetime, io
    import mediasort.dates as d
    monkeypatch.setattr(d, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = _session_ouverte(client, h)
    contenu = b"une vraie photo"
    client.post("/sync/upload", headers=h,
               data={"session": session, "path": "DCIM/Camera/a.jpg"},
               files={"file": ("a.jpg", io.BytesIO(contenu), "image/jpeg")})

    r = client.post("/sync/commit", headers=h, json={"session": session})

    assert r.status_code == 200
    assert "mouvements" not in r.json()


def test_un_journal_en_panne_ne_fait_pas_echouer_le_commit(tmp_path, monkeypatch):
    """Point d'attention 3 : l'horizon doit avancer quand même."""
    a, client = _client(tmp_path, monkeypatch)
    # APRÈS _client, qui pose toujours un chemin sain : le journal ne s'ouvre
    # qu'à la première écriture, donc ce chemin illisible est bien celui
    # qu'il essaiera d'ouvrir.
    monkeypatch.setattr(a.config, "JOURNAL_DB", tmp_path / "absent" / "sous" / "j.db")
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    r = client.post("/sync/commit", headers=h, json={
        "session": session, "horizons": {"DCIM/Camera": 1.0e9}})

    assert r.status_code == 200
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1.0e9}
    # Le journal n'a jamais pu s'ouvrir : c'est bien LUI qui était en panne,
    # pas un test qui passerait sur un journal sain.
    assert a._journal_ouvert is None


def test_un_journal_verrouille_ne_ralentit_pas_tout_le_tri(tmp_path, monkeypatch):
    """M3 (relecture finale) : disjoncteur par commit.

    Un outil extérieur qui tient la base (DB Browser, une sauvegarde) fait
    attendre CHAQUE écriture 5 s avant d'échouer — sous le verrou du tri :
    ~80 min de plus sur un commit de 953 fichiers, le téléphone abandonnait
    à 30 min. Au premier échec d'un mouvement, les suivants de ce tri ne sont
    plus tentés ; le commit répond 200 et l'horizon avance quand même.
    """
    import sqlite3
    import mediasort.dates as d
    monkeypatch.setattr(d, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = _session_ouverte(client, h)
    for nom in ("a.jpg", "b.jpg", "c.jpg"):
        assert _envoyer(client, h, session, f"DCIM/Camera/{nom}",
                        f"photo {nom}".encode()).status_code == 200

    appels = []
    def verrouille(session, m):
        appels.append(m["origine"])
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(a.journal(), "ajouter_mouvement", verrouille)

    r = client.post("/sync/commit", headers=h, json={
        "session": session, "horizons": {"DCIM/Camera": 1.0e9}})

    assert r.status_code == 200 and r.json()["sorted"] == 3
    assert len(appels) == 1, appels
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1.0e9}


def test_une_extension_refusee_a_l_envoi_est_journalisee(tmp_path, monkeypatch):
    """Un refus à l'upload (avant même le trieur) laisse une trace nominative."""
    import io
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = _session_ouverte(client, h)

    refuse = client.post("/sync/upload", headers=h,
                         data={"session": session, "path": "notes.txt"},
                         files={"file": ("notes.txt", io.BytesIO(b"x"), "text/plain")})
    assert refuse.status_code == 400

    client.post("/sync/commit", headers=h, json={"session": session, "synchro": "s1"})

    assert [m["issue"] for m in a.journal().mouvements("s1")] == ["refuse_envoi"]


@pytest.mark.parametrize("champ", ["envoyes", "refuses", "echecs"])
def test_le_bilan_de_l_app_est_borne(champ, tmp_path, monkeypatch):
    """M2 (relecture finale) : un nombre négatif ou démesuré n'a rien à faire
    dans le journal. 10**30 faisait même lever SQLite (entier de plus de 64
    bits) au milieu de l'écriture du commit. Refusé dès la lecture (422)."""
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}

    for valeur in (-1, 2**31, 10**30):
        session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]
        r = client.post("/sync/commit", headers=h,
                        json={"session": session, "bilan_app": {champ: valeur}})
        assert r.status_code == 422, (champ, valeur)

    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]
    r = client.post("/sync/commit", headers=h,
                    json={"session": session, "bilan_app": {champ: 2**31 - 1}})
    assert r.status_code == 200


def test_un_identifiant_de_synchro_hors_norme_est_remplace(tmp_path, monkeypatch):
    """Un identifiant fantaisiste ou trop long ne doit pas atteindre la base tel quel."""
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    r = client.post("/sync/commit", headers=h,
                    json={"session": session, "synchro": "x" * 500})

    assert r.status_code == 200
    assert len(a.journal().synchros()[0]["id"]) <= 64


@pytest.mark.parametrize("contenu,description", [
    (b"-----BEGIN CERTIFICATE-----\nMIIDazCCAlOgAwIBAgIU\n", "PEM tronqué"),
    (b"", "fichier vide"),
    (b"\x00\x01\x02\xff\xfe", "contenu binaire"),
])
def test_un_certificat_abime_ne_casse_pas_la_page_d_appairage(
        contenu, description, tmp_path, monkeypatch):
    """Troisième occurrence de « fichier corrompu → erreur 500 » dans ce lot.

    `tls.empreinte_certificat` lit le fichier en texte puis le décode : un PEM
    tronqué ou vide lève ValueError, un contenu binaire UnicodeDecodeError.
    Seul OSError était attrapé, donc `/pair` répondait 500. Le cas est
    atteignable : un `openssl req` interrompu ou une copie de migration coupée
    laisse un PEM tronqué.

    Comme pour un certificat absent, on veut une page qui s'affiche et une
    empreinte nulle — l'application saura simplement que le serveur n'est pas
    épinglable.
    """
    import json
    cert = tmp_path / "cert.pem"
    cert.write_bytes(contenu)
    monkeypatch.setenv("CERT_FILE", str(cert))
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)

    r = client.get("/pair", headers=entetes)

    assert r.status_code == 200, description
    assert json.loads(a.charge_appairage())["cert_sha256"] is None, description


def test_un_horodatage_futur_est_ramene_a_maintenant(tmp_path, monkeypatch):
    """Une borne haute sur l'horizon : sinon un dossier se referme pour toujours.

    Un horodatage dans le futur — horloge d'appareil photo mal réglée, bug de
    l'application, valeur aberrante — enregistré tel quel fermerait
    définitivement le dossier : toutes les photos suivantes seraient sous
    l'horizon et ne seraient plus jamais proposées. La direction inverse est
    bénigne : un horizon qui recule fait reproposer des fichiers déjà connus,
    que l'anti-doublon écarte sans les transférer.
    """
    import time
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]
    an_2100 = 4102444800.0

    avant = time.time()
    r = client.post("/sync/commit", headers=h, json={
        "session": session, "horizons": {"DCIM/Camera": an_2100}})
    apres = time.time()

    assert r.status_code == 200
    enregistre = a.devices().get_horizons(dev_id)["DCIM/Camera"]
    assert avant <= enregistre <= apres, enregistre

    # ...et la synchro suivante fonctionne normalement : le dossier n'est pas
    # refermé, un horodatage plausible est enregistré tel quel.
    session2 = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]
    client.post("/sync/commit", headers=h, json={
        "session": session2, "horizons": {"DCIM/Camera": 1726574400.0}})
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1726574400.0}


def _horizons_bruts(client, entetes, session, corps_json):
    """Envoie un commit dont le corps JSON est écrit à la main.

    `json=` refuserait NaN et ±Infinity : ce ne sont pas du JSON standard.
    L'application Android, elle, peut parfaitement les produire — c'est le
    cas reproduit — et FastAPI les accepte à la lecture.
    """
    return client.post("/sync/commit", headers={**entetes,
                                                "Content-Type": "application/json"},
                       content=corps_json)


def test_un_horizon_non_fini_est_ignore_sans_bloquer_les_autres_dossiers(
        tmp_path, monkeypatch):
    """NaN est la seule valeur que min() ne sait pas borner : min(nan, x) vaut
    nan. SQLite l'enregistre en NULL, la contrainte NOT NULL de
    horizons.dernier_ts lève, et rien ne l'attrape : le client reçoit une
    erreur 500 et les horizons sont écrits À MOITIÉ — le dossier fautif ne
    progresse alors jamais.

    On ignore le dossier fautif plutôt que de rejeter tout l'envoi : un
    horodatage aberrant sur un dossier ne doit pas faire échouer la synchro
    des autres, ni empêcher de valider des médias déjà rangés.
    """
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    r = _horizons_bruts(client, h, session,
                        '{"session": "%s", "horizons":'
                        ' {"DCIM/Camera": 1726574400.0, "Zbug": NaN}}' % session)

    assert r.status_code == 200
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1726574400.0}


def test_un_horizon_moins_l_infini_ne_casse_pas_le_contrat_de_l_app(
        tmp_path, monkeypatch):
    """-Infinity passait la borne (min(-inf, now) == -inf), était enregistré,
    et GET /sync/horizon le rendait en `null` — ce qui casse le contrat
    `dossiers: dict[str, float]` que l'application Android code en dur.
    """
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    r = _horizons_bruts(client, h, session,
                        '{"session": "%s", "horizons":'
                        ' {"DCIM/Camera": 1726574400.0, "Zbug": -Infinity}}' % session)

    assert r.status_code == 200
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1726574400.0}
    dossiers = client.get("/sync/horizon", headers=h).json()["dossiers"]
    assert "Zbug" not in dossiers
    assert all(isinstance(ts, float) for ts in dossiers.values()), dossiers


def test_un_horizon_plus_l_infini_reste_ramene_a_maintenant(tmp_path, monkeypatch):
    """Ce qui marchait déjà doit continuer : +Infinity est borné, pas ignoré."""
    import time
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    avant = time.time()
    r = _horizons_bruts(client, h, session,
                        '{"session": "%s", "horizons": {"DCIM/Camera": Infinity}}'
                        % session)
    apres = time.time()

    assert r.status_code == 200
    enregistre = a.devices().get_horizons(dev_id)["DCIM/Camera"]
    assert avant <= enregistre <= apres, enregistre


# --- documentation interactive de FastAPI ------------------------------------
#
# Constaté sur le NUC en service le 18/09/2026 : /docs, /redoc et
# /openapi.json répondaient 200 SANS authentification. Personne ne les avait
# ajoutées — FastAPI les publie par défaut. Elles livrent la carte complète de
# l'API (chemins, formats attendus, codes de retour) et /docs est un client
# interactif prêt à s'en servir. Rien d'autre sur ce service n'est ouvert : /,
# /pair, /devices exigent le mot de passe, /status et /sync/* un jeton
# d'appareil. C'était la seule porte sans serrure.


def test_la_documentation_interactive_n_est_pas_publiee(tmp_path, monkeypatch):
    """Les trois routes ouvertes par défaut de FastAPI doivent être fermées.

    Un 404 et non un 401 : mieux vaut que la porte n'existe pas du tout
    plutôt qu'elle annonce ce qu'elle protège.
    """
    monkeypatch.delenv("DOCS_PUBLIQUES", raising=False)
    _, client = _client(tmp_path, monkeypatch)
    for chemin in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(chemin).status_code == 404, f"{chemin} est publié"


def test_la_documentation_reste_activable_pour_le_developpement(tmp_path, monkeypatch):
    """DOCS_PUBLIQUES=1 les rouvre, sur une machine de développement.

    Sans cette porte de sortie, la seule façon de consulter le schéma serait
    de modifier le code — avec le risque de committer la réouverture et de la
    déployer sans s'en rendre compte.
    """
    monkeypatch.setenv("DOCS_PUBLIQUES", "1")
    _, client = _client(tmp_path, monkeypatch)
    assert client.get("/openapi.json").status_code == 200


# --- identifiant d'administration choisi -------------------------------------
#
# « admin » était écrit en dur. C'est le premier nom que tente n'importe quel
# balayage automatique, avec « root » et « administrator ». En changer ne
# remplace ni un mot de passe solide ni la limitation d'essais (#19) — c'est
# une serrure de plus, pas une meilleure porte — mais ça ne coûte rien et ça
# écarte le bruit de fond des attaques génériques.


def _avec_identifiants(tmp_path, monkeypatch, utilisateur=None,
                       mot_de_passe="le-mot-de-passe"):
    """Prépare le fichier de mot de passe et, si demandé, celui d'identifiant."""
    import base64
    from phototheque import adminauth
    fichier = tmp_path / "admin"
    fichier.write_text(adminauth.empreinte(mot_de_passe, iterations=1000))
    monkeypatch.setenv("ADMIN_FILE", str(fichier))
    if utilisateur is not None:
        f_util = tmp_path / "utilisateur"
        f_util.write_text(utilisateur)
        monkeypatch.setenv("ADMIN_USER_FILE", str(f_util))
    else:
        monkeypatch.setenv("ADMIN_USER_FILE", str(tmp_path / "jamais-cree"))

    def entetes(util, mdp=mot_de_passe):
        jeton = base64.b64encode(f"{util}:{mdp}".encode()).decode()
        return {"Authorization": f"Basic {jeton}"}
    return entetes


def test_un_identifiant_choisi_remplace_admin(tmp_path, monkeypatch):
    """Le nom choisi ouvre ; « admin » ne doit plus rien ouvrir du tout.

    La seconde moitié est l'essentiel : si « admin » continuait de marcher en
    parallèle, changer d'identifiant n'apporterait strictement rien.
    """
    entetes = _avec_identifiants(tmp_path, monkeypatch, utilisateur="ken")
    _, client = _client(tmp_path, monkeypatch)
    assert client.get("/", headers=entetes("ken")).status_code == 200
    assert client.get("/", headers=entetes("admin")).status_code == 401


def test_sans_fichier_d_identifiant_admin_reste_valable(tmp_path, monkeypatch):
    """Compatibilité : une installation existante ne doit pas se fermer.

    Le fichier d'identifiant n'existe sur aucune installation antérieure au
    18/09/2026. Son absence doit valoir « admin », pas « personne ».
    """
    entetes = _avec_identifiants(tmp_path, monkeypatch, utilisateur=None)
    _, client = _client(tmp_path, monkeypatch)
    assert client.get("/", headers=entetes("admin")).status_code == 200


def test_un_fichier_d_identifiant_vide_retombe_sur_admin(tmp_path, monkeypatch):
    """Un fichier vide ou blanc ne doit verrouiller personne dehors.

    Une écriture interrompue, un fichier créé par mégarde : sans ce filet,
    plus AUCUN identifiant ne fonctionnerait et il faudrait un accès SSH pour
    s'en sortir.
    """
    entetes = _avec_identifiants(tmp_path, monkeypatch, utilisateur="   \n")
    _, client = _client(tmp_path, monkeypatch)
    assert client.get("/", headers=entetes("admin")).status_code == 200


def test_l_identifiant_est_insensible_aux_espaces_autour(tmp_path, monkeypatch):
    """Un saut de ligne final ne doit pas rendre l'identifiant intapable.

    Le fichier est écrit par un script shell ; une fin de ligne s'y glisse
    facilement, et l'utilisateur ne pourrait jamais taper l'espace en trop.
    """
    entetes = _avec_identifiants(tmp_path, monkeypatch, utilisateur="ken\n")
    _, client = _client(tmp_path, monkeypatch)
    assert client.get("/", headers=entetes("ken")).status_code == 200


# --- limitation des essais sur l'administration (issue #19) ------------------


def _client_depuis(tmp_path, monkeypatch, ip="192.168.1.50"):
    """Comme _client, mais en se faisant passer pour une machine donnée."""
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path))
    monkeypatch.setenv("CATALOG_DB", str(tmp_path / "cat.db"))
    monkeypatch.setenv("INCOMING_DIR", str(tmp_path / "incoming"))
    monkeypatch.setenv("DEVICES_DB", str(tmp_path / "dev.db"))
    # Voir le commentaire équivalent dans _client.
    monkeypatch.setenv("JOURNAL_DB", str(tmp_path / "journal.db"))
    import phototheque.config as c; importlib.reload(c)
    import phototheque.app as a; importlib.reload(a)
    return a, TestClient(a.app, client=(ip, 12345))


def _entetes(utilisateur, mot_de_passe):
    import base64
    jeton = base64.b64encode(f"{utilisateur}:{mot_de_passe}".encode()).decode()
    return {"Authorization": f"Basic {jeton}"}


def _pose_mot_de_passe(tmp_path, monkeypatch, mot_de_passe="le-bon-mot-de-passe"):
    from phototheque import adminauth
    fichier = tmp_path / "admin"
    fichier.write_text(adminauth.empreinte(mot_de_passe, iterations=1000))
    monkeypatch.setenv("ADMIN_FILE", str(fichier))
    monkeypatch.setenv("ADMIN_USER_FILE", str(tmp_path / "jamais-cree"))


def test_apres_trop_d_essais_le_refus_ne_calcule_plus_d_empreinte(tmp_path, monkeypatch):
    """LE point de l'issue #19 : ne plus payer 100 ms de calcul par essai.

    Le coût de l'empreinte est supporté par le SERVEUR, sur les deux cœurs du
    NUC, dans le processus qui fait aussi le tri des médias. Refuser en
    calculant quand même laisserait intact le levier de saturation ; c'est
    l'absence de calcul qui protège, pas le refus.
    """
    _pose_mot_de_passe(tmp_path, monkeypatch)
    a, client = _client_depuis(tmp_path, monkeypatch)

    for _ in range(a.essais.SEUIL):
        client.get("/", headers=_entetes("admin", "mauvais"))

    appels = []
    vrai_verifier = a.adminauth.verifier
    monkeypatch.setattr(a.adminauth, "verifier",
                        lambda *args, **kw: appels.append(1) or vrai_verifier(*args, **kw))

    r = client.get("/", headers=_entetes("admin", "mauvais"))
    assert r.status_code == 429, r.status_code
    assert appels == [], "une empreinte a été calculée malgré le refus"
    assert r.headers.get("Retry-After"), "pas d'indication du délai à attendre"


def test_le_bon_mot_de_passe_passe_avant_le_seuil(tmp_path, monkeypatch):
    """Quelques fautes de frappe ne doivent pas gêner le mainteneur."""
    _pose_mot_de_passe(tmp_path, monkeypatch)
    a, client = _client_depuis(tmp_path, monkeypatch)
    for _ in range(a.essais.SEUIL - 1):
        client.get("/", headers=_entetes("admin", "mauvais"))
    assert client.get("/", headers=_entetes("admin", "le-bon-mot-de-passe")).status_code == 200


def test_une_connexion_reussie_efface_les_echecs(tmp_path, monkeypatch):
    """Sinon les erreurs de la veille finiraient par fermer la porte."""
    _pose_mot_de_passe(tmp_path, monkeypatch)
    a, client = _client_depuis(tmp_path, monkeypatch)
    for _ in range(a.essais.SEUIL - 1):
        client.get("/", headers=_entetes("admin", "mauvais"))
    assert client.get("/", headers=_entetes("admin", "le-bon-mot-de-passe")).status_code == 200
    for _ in range(a.essais.SEUIL - 1):
        client.get("/", headers=_entetes("admin", "mauvais"))
    assert client.get("/", headers=_entetes("admin", "le-bon-mot-de-passe")).status_code == 200


def test_l_acharnement_d_une_machine_ne_ferme_pas_la_porte_aux_autres(tmp_path, monkeypatch):
    """Sans séparation par source, on offrirait le déni de service à l'attaquant.

    N'importe qui sur le réseau enfermerait le mainteneur dehors avec quelques
    essais ratés — exactement ce que la limitation est censée empêcher.
    """
    _pose_mot_de_passe(tmp_path, monkeypatch)
    a, intrus = _client_depuis(tmp_path, monkeypatch, ip="192.168.1.99")
    for _ in range(a.essais.SEUIL + 2):
        intrus.get("/", headers=_entetes("admin", "mauvais"))
    assert intrus.get("/", headers=_entetes("admin", "mauvais")).status_code == 429

    mainteneur = TestClient(a.app, client=("192.168.1.50", 999))
    assert mainteneur.get("/", headers=_entetes("admin", "le-bon-mot-de-passe")).status_code == 200


def test_naviguer_sans_identifiants_ne_declenche_jamais_la_limitation(tmp_path, monkeypatch):
    """Le passage obligé du navigateur ne doit pas être compté comme un échec.

    Un navigateur envoie TOUJOURS une première requête sans identifiants et
    n'affiche sa fenêtre de connexion qu'après avoir reçu le 401. Compter ces
    requêtes épuiserait le quota du mainteneur en navigation parfaitement
    normale : ouvrir quelques pages, recharger, et l'administration se
    fermerait toute seule — sans qu'aucun mot de passe n'ait été tenté.
    """
    _pose_mot_de_passe(tmp_path, monkeypatch)
    a, client = _client_depuis(tmp_path, monkeypatch)

    for _ in range(a.essais.SEUIL * 4):
        assert client.get("/").status_code == 401

    # Le bon mot de passe doit toujours passer : rien n'a été décompté.
    assert client.get("/", headers=_entetes("admin", "le-bon-mot-de-passe")).status_code == 200


def _envoyer(client, entetes, session, chemin, contenu):
    """Téléverse un fichier dans une session déjà ouverte."""
    return client.post("/sync/upload", headers=entetes,
                       data={"session": session, "path": chemin},
                       files={"file": (chemin.rsplit("/", 1)[-1],
                                       io.BytesIO(contenu), "image/jpeg")})


def test_le_commit_met_a_l_abri_le_fichier_qu_il_n_a_pas_su_ranger(tmp_path, monkeypatch):
    """Issue #16 : le nettoyage de session DÉTRUISAIT les fichiers en échec.

    L'horizon n'avançait pas, donc le téléphone reproposait le média — mais
    cette garantie repose sur un tiers. Une application qui libère la place
    après envoi, un DCIM vidé à la main, et l'unique copie restante avait
    disparu, détruite par le serveur lui-même.
    """
    import mediasort.dates as d, mediasort.sorter as s
    monkeypatch.setattr(d, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    vraie_copie = s.copy_and_hash
    def copie_capricieuse(source, destination):
        if source.name == "casse.jpg":
            raise OSError(28, "No space left on device")
        return vraie_copie(source, destination)
    monkeypatch.setattr(s, "copy_and_hash", copie_capricieuse)

    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel"); h = {"Authorization": f"Bearer {secret}"}
    bon, casse = b"une photo qui passe", b"une photo qui casse"
    plan = client.post("/sync/plan", headers=h, json={"files": [
        {"path": "Pictures/bon.jpg", "size": len(bon),
         "hash": hashlib.sha256(bon).hexdigest()},
        {"path": "Pictures/casse.jpg", "size": len(casse),
         "hash": hashlib.sha256(casse).hexdigest()}]})
    session = plan.json()["session"]
    assert _envoyer(client, h, session, "Pictures/bon.jpg", bon).status_code == 200
    assert _envoyer(client, h, session, "Pictures/casse.jpg", casse).status_code == 200

    r = client.post("/sync/commit", headers=h,
                    json={"session": session, "horizons": {"Pictures": 1726574400.0}})

    assert r.status_code == 200 and r.json()["errors"] == 1
    # LE point de l'issue : le média existe encore quelque part sur le NUC.
    abri = a.config.INCOMING_DIR / "_echecs"
    survivants = a.quarantaine.lister(abri)
    assert [e["fichier"] for e in survivants] == ["Pictures/casse.jpg"]
    assert (abri / "Pictures/casse.jpg").read_bytes() == casse
    assert "space" in survivants[0]["raison"]
    # Le dossier de session, lui, est bien nettoyé : rien n'est dupliqué.
    assert not (a.config.INCOMING_DIR / session).exists()
    # Et le fichier correctement rangé est en bibliothèque, pas en quarantaine.
    assert (tmp_path / "Photos" / "2023" / "05 MAI" / "bon.jpg").read_bytes() == bon
    # L'horizon n'avance toujours pas : le téléphone reproposera le dossier.
    assert a.devices().get_horizons(dev_id) == {}


def test_admin_annonce_les_medias_non_ranges(tmp_path, monkeypatch):
    """Un média en quarantaine doit se VOIR : nom, raison, et le compte."""
    html = web.admin_html(
        devices=[], disk={"total": 1, "utilise": 0, "libre": 1, "pourcentage_utilise": 0},
        media={"photos": 0, "videos": 0},
        echecs=[{"fichier": "Pictures/casse.jpg", "raison": "No space left on device",
                 "date": "2026-09-23T18:00:00+02:00", "octets": 1234}])

    assert "Pictures/casse.jpg" in html
    assert "No space left on device" in html
    assert "non rang" in html.lower()          # « Médias non rangés »


def test_admin_ne_parle_pas_de_quarantaine_quand_il_n_y_en_a_pas(tmp_path):
    """Marche normale : le bloc n'existe pas, il n'inquiète personne pour rien."""
    html = web.admin_html(
        devices=[], disk={"total": 1, "utilise": 0, "libre": 1, "pourcentage_utilise": 0},
        media={"photos": 0, "videos": 0}, echecs=[])

    assert "non rang" not in html.lower()


def test_la_purge_des_echecs_exige_le_mot_de_passe(tmp_path, monkeypatch):
    """Sans mot de passe, on ne peut pas faire supprimer des médias au serveur."""
    _pose_mot_de_passe(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    assert client.post("/echecs/purge").status_code == 401


def test_la_purge_des_echecs_vide_la_quarantaine(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    abri = a.config.INCOMING_DIR / "quarantaine_essai"
    session = a.config.INCOMING_DIR / ("b" * 32)
    session.mkdir(parents=True)
    (session / "a.jpg").write_bytes(b"photo")
    a.quarantaine.mettre_de_cote(
        session, [{"fichier": "a.jpg", "raison": "disque plein"}],
        a.config.INCOMING_DIR / a.quarantaine.DOSSIER)

    r = client.post("/echecs/purge", headers=entetes)

    assert r.status_code == 200
    assert a.quarantaine.lister(a.config.INCOMING_DIR / a.quarantaine.DOSSIER) == []


def test_la_page_d_admin_montre_les_medias_non_ranges(tmp_path, monkeypatch):
    """Le bloc existe (testé plus haut) — encore faut-il que la page l'alimente.

    Sans ce test, retirer l'appel à quarantaine.lister() au moment de construire
    la page laissait TOUTE la suite verte : le média était bien sauvé sur le
    disque, mais plus personne ne pouvait le savoir.
    """
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    session = a.config.INCOMING_DIR / ("c" * 32)
    (session / "Pictures").mkdir(parents=True)
    (session / "Pictures" / "casse.jpg").write_bytes(b"photo")
    a.quarantaine.mettre_de_cote(
        session, [{"fichier": "Pictures/casse.jpg", "raison": "disque plein"}],
        a.config.INCOMING_DIR / a.quarantaine.DOSSIER)

    html = client.get("/", headers=entetes).text

    assert "Pictures/casse.jpg" in html
    assert "disque plein" in html


def test_un_doublon_n_est_pas_mis_en_quarantaine(tmp_path, monkeypatch):
    """La quarantaine ne retient QUE les échecs.

    Ce qui reste dans le dossier de session après un tri contient aussi les
    doublons et le bruit exclu : le trieur ne les efface pas, il les ignore.
    Les mettre à l'abri remplirait le disque de médias déjà rangés — et ferait
    croire à une avalanche de pannes.
    """
    import mediasort.dates as d
    monkeypatch.setattr(d, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel"); h = {"Authorization": f"Bearer {secret}"}
    session = a.config.INCOMING_DIR / ("d" * 32)
    session.mkdir(parents=True)
    # Deux fois le même contenu : le premier est rangé, le second est un doublon.
    (session / "a.jpg").write_bytes(b"exactement la meme photo")
    (session / "b.jpg").write_bytes(b"exactement la meme photo")

    r = client.post("/sync/commit", headers=h, json={"session": session.name})

    assert r.status_code == 200
    assert r.json()["sorted"] == 1 and r.json()["duplicates"] == 1
    assert r.json()["errors"] == 0
    assert a.quarantaine.lister(a.config.INCOMING_DIR / a.quarantaine.DOSSIER) == []
    # Le doublon a bien été détruit avec la session : rien n'est dupliqué.
    assert not session.exists()


def test_le_telephone_peut_se_desappairer_lui_meme(tmp_path, monkeypatch):
    """Le téléphone n'a qu'un jeton d'appareil, pas le mot de passe d'admin.

    Sans cette route il ne PEUT PAS se retirer : la seule révocation existante
    est derrière require_admin. Et le jour où il en a besoin — certificat du
    NUC change — le TLS échoue avant le HTTP, aucun 401 n'arrive jamais,
    oublier() n'est pas déclenché et l'écran de scan est inatteignable une fois
    appairé. L'application était bloquée définitivement.
    """
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    a.devices().set_horizon(dev_id, "DCIM/Camera", 1726574400.0)

    r = client.post("/sync/desappairer", headers=h)

    assert r.status_code == 200
    assert client.get("/status", headers=h).status_code == 401
    assert a.devices().get_horizons(dev_id) == {}


def test_le_desappairage_exige_un_jeton_d_appareil(tmp_path, monkeypatch):
    """Sans jeton, personne ne fait déconnecter le téléphone de quelqu'un."""
    a, client = _client(tmp_path, monkeypatch)
    assert client.post("/sync/desappairer").status_code == 401


# --- issue #30 : purge des sessions abandonnées et POST /sync/abandon -------


def test_sync_abandon_exige_un_appareil(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    assert client.post("/sync/abandon", json={"session": "a" * 32}).status_code == 401


def test_sync_abandon_supprime_la_session_et_journalise(tmp_path, monkeypatch):
    """Le bouton « Interrompre » : la session en cours disparaît, sans attendre
    les 24 h de la purge automatique, et laisse une trace nominative."""
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = _session_ouverte(client, h)
    dossier = a.config.INCOMING_DIR / session
    dossier.mkdir(parents=True)
    (dossier / "DCIM").mkdir()
    (dossier / "DCIM" / "v.mp4.partiel").write_bytes(b"12345")

    r = client.post("/sync/abandon", headers=h, json={"session": session})

    assert r.status_code == 200
    assert r.json() == {"supprimes": 1, "octets": 5}
    assert not dossier.exists()
    evenements = a.journal().evenements()
    assert any(e["type"] == "abandon" and e["appareil"] == dev_id for e in evenements)


def test_sync_abandon_refuse_un_identifiant_hors_norme(tmp_path, monkeypatch):
    """Un identifiant fantaisiste ne doit ni supprimer, ni faire planter la route."""
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}

    r = client.post("/sync/abandon", headers=h, json={"session": "../../etc"})

    assert r.status_code == 400


def test_le_demarrage_purge_et_se_journalise(tmp_path, monkeypatch):
    """Au lancement du service : une trace de démarrage, et les sessions
    abandonnées depuis plus de 24 h disparaissent sans attendre un commit."""
    a, client = _client(tmp_path, monkeypatch)
    vieille = a.config.INCOMING_DIR / ("e" * 32)
    vieille.mkdir(parents=True)
    (vieille / "x.jpg").write_bytes(b"1")
    import os, time
    t = time.time() - 25 * 3600
    for p in [vieille, *vieille.rglob("*")]:
        os.utime(p, (t, t))

    with TestClient(a.app):            # le `with` déclenche le lifespan
        pass

    types = [e["type"] for e in a.journal().evenements()]
    assert "demarrage" in types and "purge" in types
    assert not vieille.exists()


def test_le_commit_purge_aussi_les_sessions_abandonnees(tmp_path, monkeypatch):
    """Pas seulement au démarrage : chaque commit purge aussi (spec §5), sans
    attendre qu'on relance le service pour libérer l'espace."""
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    vieille = a.config.INCOMING_DIR / ("f" * 32)
    vieille.mkdir(parents=True)
    (vieille / "x.jpg").write_bytes(b"1")
    import os, time
    t = time.time() - 25 * 3600
    for p in [vieille, *vieille.rglob("*")]:
        os.utime(p, (t, t))
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    r = client.post("/sync/commit", headers=h, json={"session": session})

    assert r.status_code == 200
    assert not vieille.exists()


def test_une_purge_en_panne_ne_fait_pas_echouer_le_commit(tmp_path, monkeypatch):
    """Une purge qui casse (disque, permissions...) ne doit ni faire échouer le
    commit, ni empêcher l'horizon d'avancer — la purge n'est qu'un ménage."""
    a, client = _client(tmp_path, monkeypatch)

    def _casse(*args, **kwargs):
        raise OSError("panne simulee")
    monkeypatch.setattr(a.sessions, "purger_abandonnees", _casse)

    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    r = client.post("/sync/commit", headers=h, json={
        "session": session, "horizons": {"DCIM/Camera": 1.0e9}})

    assert r.status_code == 200
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1.0e9}


# --- relecture round 1 : les deux garde-fous de purge attrapent Exception ----


def test_une_exception_quelconque_au_demarrage_ne_bloque_pas_le_service(tmp_path, monkeypatch):
    """Reglage du controleur (round 1, point 1) : le garde-fou du demarrage
    doit attraper N'IMPORTE QUELLE exception, pas seulement OSError — une
    erreur de programmation dans la purge ne doit pas non plus empecher le
    service de demarrer, meme regle que _journaliser."""
    a, client = _client(tmp_path, monkeypatch)

    def _casse(*args, **kwargs):
        raise RuntimeError("panne non-OSError simulee")
    monkeypatch.setattr(a.sessions, "purger_abandonnees", _casse)

    with TestClient(a.app):            # ne doit pas lever
        pass

    types = [e["type"] for e in a.journal().evenements()]
    assert "demarrage" in types


def test_une_exception_quelconque_ne_fait_pas_echouer_le_commit(tmp_path, monkeypatch):
    """Meme reglage cote sync_commit : n'importe quelle exception de purge,
    pas seulement OSError, ne doit ni casser la reponse ni bloquer l'horizon."""
    a, client = _client(tmp_path, monkeypatch)

    def _casse(*args, **kwargs):
        raise RuntimeError("panne non-OSError simulee")
    monkeypatch.setattr(a.sessions, "purger_abandonnees", _casse)

    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=h, json={"files": []}).json()["session"]

    r = client.post("/sync/commit", headers=h, json={
        "session": session, "horizons": {"DCIM/Camera": 1.0e9}})

    assert r.status_code == 200
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1.0e9}


# --- issue #30 (tache 5) : evenements d'appairage, de revocation et --------
# --- d'authentification -----------------------------------------------------


def test_une_requete_sans_identifiants_n_est_pas_un_echec_journalise(tmp_path, monkeypatch):
    """Spec §8.9 : le navigateur en envoie toujours une avant sa fenetre.

    Compter ce passage oblige comme un echec journalise donnerait une fausse
    image d'acharnement pour une simple ouverture de page.
    """
    _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/")
    assert all(e["type"] != "auth_echec" for e in a.journal().evenements())


def test_un_mauvais_mot_de_passe_est_journalise(tmp_path, monkeypatch):
    _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/", headers=_entetes("admin", "faux"))
    assert any(e["type"] == "auth_echec" for e in a.journal().evenements())


def test_appairage_confirmation_et_revocation_sont_journalises(tmp_path, monkeypatch):
    """Les trois temps d'un appairage laissent chacun leur trace.

    GET /pair cree un appairage EN ATTENTE ("appairage"), le premier usage du
    secret par le telephone le CONFIRME ("confirmation"), et la revocation
    par l'administration cloture l'appareil ("revocation").
    """
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)

    client.get("/pair", headers=entetes)
    dev_id, secret = a._appairage_en_cours
    client.get("/sync/horizon", headers={"Authorization": f"Bearer {secret}"})
    client.post(f"/devices/{dev_id}/revoke", headers=entetes)

    types = [e["type"] for e in a.journal().evenements()]
    assert {"appairage", "confirmation", "revocation"} <= set(types)


def test_le_desappairage_journalise_une_revocation(tmp_path, monkeypatch):
    """Le telephone peut se retirer lui-meme (lot 2) : trace distincte de
    celle d'une revocation faite depuis l'administration."""
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}

    r = client.post("/sync/desappairer", headers=h)

    assert r.status_code == 200 and r.json() == {"retire": True}
    evenements = a.journal().evenements()
    assert any(e["type"] == "revocation" and e["appareil"] == dev_id
              and e["detail"] == "demandée par le téléphone" for e in evenements)
