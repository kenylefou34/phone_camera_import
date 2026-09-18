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
