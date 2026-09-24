"""Verrouille le contrat décrit dans docs/CONTRAT-APP.md (issue #15).

Ce fichier n'existe pas pour tester le serveur — les autres s'en chargent — mais
pour que toute modification d'un endpoint qui changerait la FORME des réponses
fasse échouer la suite ici, dans le dépôt où la modification est faite.
L'application Android, elle, code ces formes en dur.
"""

import hashlib
import io


def test_le_qr_porte_exactement_trois_champs(tmp_path, monkeypatch):
    from phototheque import pairing
    charge = pairing.pairing_payload("https://x:8787", "jeton", "ab" * 32)
    assert set(charge) == {"url", "token", "cert_sha256"}, (
        "l'application code ces trois champs en dur ; en ajouter ou en retirer "
        "casse l'appairage de toutes les versions déjà installées")


def test_horizon_renvoie_depuis_et_dossiers(tmp_path, monkeypatch):
    from tests.test_app import _client          # réutilise la fixture existante
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    r = client.get("/sync/horizon", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200
    corps = r.json()
    assert set(corps) == {"depuis", "dossiers"}
    assert isinstance(corps["dossiers"], dict)


def test_plan_renvoie_session_et_empreintes(tmp_path, monkeypatch):
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    entetes = {"Authorization": f"Bearer {secret}"}
    empreinte = hashlib.sha256(b"photo").hexdigest()
    r = client.post("/sync/plan", headers=entetes, json={
        "files": [{"path": "DCIM/a.jpg", "size": 5, "hash": empreinte}]})
    assert r.status_code == 200
    corps = r.json()
    assert set(corps) == {"session", "needed"}
    assert len(corps["session"]) == 32
    # « needed » contient des EMPREINTES, pas des chemins : l'application refait
    # la correspondance elle-même (CONTRAT-APP.md, section 4.2).
    assert corps["needed"] == [empreinte]


def test_les_champs_path_et_size_restent_obligatoires(tmp_path, monkeypatch):
    """Les retirer du contrat sans prévenir donnerait un 422 incompréhensible
    côté téléphone. Voir issue #22 avant de toucher à ce point."""
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    r = client.post("/sync/plan", headers={"Authorization": f"Bearer {secret}"},
                    json={"files": [{"hash": "ab" * 32}]})
    assert r.status_code == 422


def test_une_extension_inconnue_repond_400_et_non_500(tmp_path, monkeypatch):
    """L'application doit POURSUIVRE la synchro sur un 400. Un 500 la ferait
    au contraire s'arrêter et bloquerait l'horizon du dossier."""
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    r = client.post("/sync/upload",
                    headers={"Authorization": f"Bearer {secret}"},
                    data={"session": "a" * 32, "path": "DCIM/note.webm"},
                    files={"file": ("note.webm", io.BytesIO(b"x"), "video/webm")})
    assert r.status_code == 400


def test_un_jeton_revoque_repond_401(tmp_path, monkeypatch):
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    ident, secret = a.devices().pair("tel")
    a.devices().revoke(ident)
    r = client.get("/sync/horizon", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 401


def test_une_session_vide_se_valide_normalement(tmp_path, monkeypatch):
    """Cas COURANT une fois la bibliothèque à jour : rien à envoyer. Répondre
    404 empêcherait l'horizon d'avancer et le téléphone rescannerait sans fin."""
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    entetes = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=entetes, json={"files": []}).json()["session"]
    r = client.post("/sync/commit", headers=entetes,
                    json={"session": session, "horizons": {}})
    assert r.status_code == 200
    assert r.json()["errors"] == 0


def test_horizon_melange_bien_une_date_iso_et_des_timestamps(tmp_path, monkeypatch):
    """Deux unités dans la même réponse, et l'application les code en dur.

    `depuis` est une DATE ISO, les valeurs de `dossiers` sont des timestamps
    Unix flottants (CONTRAT-APP.md, section 4.1). Changer l'une des deux ferait
    échouer le décodage côté téléphone — ou pire, passerait et ferait avancer un
    horizon de trente ans.
    """
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    ident, secret = a.devices().pair("tel")
    a.devices().set_horizon_initial(ident, "2026-09-01")
    a.devices().set_horizon(ident, "DCIM/Camera", 1789000000.0)

    corps = client.get("/sync/horizon",
                       headers={"Authorization": f"Bearer {secret}"}).json()
    assert corps["depuis"] == "2026-09-01"          # date ISO, jamais un nombre
    assert isinstance(corps["dossiers"]["DCIM/Camera"], float)


def test_le_bilan_du_commit_garde_tous_ses_champs(tmp_path, monkeypatch):
    """L'écran de détail de l'application affiche ces compteurs.

    Un champ renommé ne ferait PAS échouer la synchronisation : il
    disparaîtrait simplement de l'écran, sans message ni erreur. C'est
    exactement le genre de perte qu'on ne remarque jamais.
    """
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    entetes = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=entetes,
                          json={"files": []}).json()["session"]

    bilan = client.post("/sync/commit", headers=entetes,
                        json={"session": session, "horizons": {}}).json()
    attendus = {"sorted", "duplicates", "to_triage", "skipped", "errors",
                "photos", "videos", "whatsapp", "octets_ranges",
                "par_source_date", "par_annee_mois"}
    assert attendus <= set(bilan), f"champs disparus : {attendus - set(bilan)}"


def test_une_session_mal_formee_repond_404(tmp_path, monkeypatch):
    """L'application distingue ce cas d'un échec réseau : c'est son propre bug.

    Répondre autre chose qu'un 404 lui ferait prendre une erreur de
    programmation pour une panne passagère, et réessayer indéfiniment.
    """
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    r = client.post("/sync/commit",
                    headers={"Authorization": f"Bearer {secret}"},
                    json={"session": "pas-un-identifiant", "horizons": {}})
    assert r.status_code == 404


def test_la_destination_predite_par_l_app_correspond_au_serveur(tmp_path):
    """L'écran d'avancement annonce « → Videos/2025/09 SEPTEMBRE ».

    Cette prédiction est calculée EN DOUBLE dans l'application
    (`synchro/Destination.kt`). Ce test fige la convention côté serveur : s'il
    tombe, c'est que le serveur a changé de règle et que l'application ment
    désormais à l'écran.
    """
    import datetime
    from mediasort import classify

    class Resultat:
        def __init__(self, d): self.date = d

    attendus = [
        ("DCIM/Camera/IMG.jpg", "photo", datetime.date(2025, 9, 27),
         "Photos/2025/09 SEPTEMBRE"),
        ("DCIM/Camera/VID.mp4", "video", datetime.date(2025, 9, 27),
         "Videos/2025/09 SEPTEMBRE"),
        ("Pictures/WhatsApp/IMG.jpg", "photo", datetime.date(2025, 9, 27),
         "WhatsApp/Photos/2025/09 SEPTEMBRE"),
        ("Movies/whatsapp/VID.mp4", "video", datetime.date(2025, 9, 27),
         "WhatsApp/Videos/2025/09 SEPTEMBRE"),
        ("DCIM/Camera/a.jpg", "photo", datetime.date(2026, 1, 15),
         "Photos/2026/01 JANVIER"),
        ("DCIM/Camera/a.jpg", "photo", datetime.date(2026, 8, 15),
         "Photos/2026/08 AOUT"),
    ]
    for relatif, mtype, jour, attendu in attendus:
        chemin = classify.destination(
            tmp_path, tmp_path / relatif, Resultat(jour), mtype)
        obtenu = str(chemin.parent.relative_to(tmp_path))
        assert obtenu == attendu, f"{relatif} -> {obtenu}, attendu {attendu}"


def test_le_commit_lit_synchro_et_bilan_app_envoyes_par_l_app(tmp_path, monkeypatch):
    """Pont de contrat (tâche 7, issue #30) : POSTe le JSON produit MOT POUR
    MOT par `RequeteCommit`, tel qu'affirmé côté Kotlin par
    ContratTest.la_requete_du_commit_porte_synchro_et_bilan_app_en_snake_case
    (capturé le 24/09/2026) :

        {"session":"ssssssssssssssssssssssssssssssss",
         "horizons":{"DCIM/Camera":100.0},
         "synchro":"f47ac10b58cc4372a5670e02b2c3d479",
         "bilan_app":{"envoyes":3,"refuses":1,"echecs":2}}

    Seul le champ « session » est remplacé par une session réelle : la
    chaîne de 32 « s » que Kotlin fabrique pour le test de sérialisation
    n'est pas un hexadécimal valide, et le serveur répondrait 404
    (sessions.identifiant_valide) avant même de lire `bilan_app`.

    Vérifie deux choses à la fois :
    1. Le serveur sait lire un `bilan_app` en snake_case envoyé tel quel par
       l'application (pas de cérémonie de désérialisation côté test qui
       masquerait un décalage de nom de champ).
    2. Un échec signalé par le téléphone (`app_echecs` > 0) se voit dans
       /historique comme « en erreur » MÊME quand le serveur, lui, n'a
       constaté aucune erreur de tri (`erreurs` == 0 ici, puisque la
       session est vide) — exactement le cas que _etat_synchro (web.py)
       est censé couvrir.
    """
    from tests.test_app import _client, _avec_admin
    entetes_admin = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    entetes = {"Authorization": f"Bearer {secret}"}

    session = client.post(
        "/sync/plan", headers=entetes, json={"files": []}).json()["session"]

    corps = (
        '{"session":"%s","horizons":{"DCIM/Camera":100.0},'
        '"synchro":"f47ac10b58cc4372a5670e02b2c3d479",'
        '"bilan_app":{"envoyes":3,"refuses":1,"echecs":2}}' % session)

    r = client.post(
        "/sync/commit",
        headers={**entetes, "Content-Type": "application/json"},
        content=corps)
    assert r.status_code == 200

    ligne = a.journal().synchro("f47ac10b58cc4372a5670e02b2c3d479")
    assert ligne is not None, "la synchro doit être journalisée sous CET identifiant"
    assert ligne["id"] == "f47ac10b58cc4372a5670e02b2c3d479"
    assert ligne["app_echecs"] == 2

    page = client.get("/historique", headers=entetes_admin).text
    assert "en erreur" in page, (
        "un échec signalé par l'app doit se voir dans l'historique, même "
        "quand le serveur n'a lui-même constaté aucune erreur de tri")
