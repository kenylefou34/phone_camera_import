"""Tests du téléchargement de l'APK depuis la page d'administration.

Le NUC ne peut pas compiler l'application : ni JDK ni SDK Android, 2 cœurs et
3 Go. L'APK est donc *déposé* par `deploy/envoyer-apk.sh` depuis la machine de
compilation, et le service se contente de le servir, derrière le mot de passe.
"""

import base64
import importlib
import json

import pytest
from fastapi.testclient import TestClient

from phototheque import adminauth, apk, web


# ---------------------------------------------------------------- outillage

def _client(tmp_path, monkeypatch):
    """Service configuré pour n'écrire que dans tmp_path."""
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path))
    monkeypatch.setenv("CATALOG_DB", str(tmp_path / "cat.db"))
    monkeypatch.setenv("INCOMING_DIR", str(tmp_path / "incoming"))
    monkeypatch.setenv("DEVICES_DB", str(tmp_path / "dev.db"))
    monkeypatch.setenv("APK_FILE", str(tmp_path / "app.apk"))
    import phototheque.config as c; importlib.reload(c)
    import phototheque.app as a; importlib.reload(a)
    return a, TestClient(a.app)


def _avec_admin(tmp_path, monkeypatch, mot_de_passe="secret-admin"):
    fichier = tmp_path / "admin"
    fichier.write_text(adminauth.empreinte(mot_de_passe, iterations=1000))
    monkeypatch.setenv("ADMIN_FILE", str(fichier))
    jeton = base64.b64encode(f"admin:{mot_de_passe}".encode()).decode()
    return {"Authorization": f"Basic {jeton}"}


def _deposer(tmp_path, contenu=b"PK\x03\x04 faux apk", infos=None):
    """Simule ce que depose deploy/envoyer-apk.sh."""
    fichier = tmp_path / "app.apk"
    fichier.write_bytes(contenu)
    if infos is not None:
        (tmp_path / "app.apk.infos.json").write_text(json.dumps(infos))
    return fichier


INFOS = {
    "version": "1.0",
    "version_code": 3,
    "construit_le": "2026-09-21T11:04:00",
    "sha256": "a" * 64,
    "octets": 25380462,
}


# ------------------------------------------------------- le module d'infos

def test_aucun_apk_depose_ne_leve_pas(tmp_path):
    """Un service fraîchement installé n'a pas d'APK : ce n'est pas une panne."""
    assert apk.infos(tmp_path / "absent.apk") is None


def test_les_infos_viennent_du_fichier_depose(tmp_path):
    fichier = _deposer(tmp_path, infos=INFOS)
    vu = apk.infos(fichier)
    assert vu["version"] == "1.0"
    assert vu["version_code"] == 3
    assert vu["sha256"] == "a" * 64


def test_sans_fichier_d_infos_on_sert_quand_meme_l_apk(tmp_path):
    """Un APK copié à la main, sans son fichier d'infos, reste téléchargeable.

    Le contraire serait absurde : le binaire est là, et le refuser parce qu'il
    manque une étiquette laisserait le mainteneur sans application ET sans
    explication.
    """
    fichier = _deposer(tmp_path, contenu=b"x" * 1234)
    vu = apk.infos(fichier)
    assert vu is not None
    assert vu["octets"] == 1234
    assert vu["version"] is None


def test_un_fichier_d_infos_illisible_n_empeche_pas_le_telechargement(tmp_path):
    """JSON corrompu : on perd l'étiquette, jamais le binaire."""
    fichier = _deposer(tmp_path, contenu=b"x" * 7)
    (tmp_path / "app.apk.infos.json").write_text("{ceci n'est pas du json")
    vu = apk.infos(fichier)
    assert vu is not None and vu["octets"] == 7 and vu["version"] is None


def test_la_taille_annoncee_est_celle_du_fichier_reel(tmp_path):
    """Le fichier d'infos ne fait pas foi sur la taille.

    Un dépôt interrompu laisserait un binaire tronqué sous une étiquette qui
    annonce la taille complète. C'est l'octet sur le disque qui compte.
    """
    fichier = _deposer(tmp_path, contenu=b"tronque", infos=INFOS)
    assert apk.infos(fichier)["octets"] == len(b"tronque")


# ------------------------------------------------------------- la route

def test_apk_absent_repond_404_en_francais(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    _, client = _client(tmp_path, monkeypatch)
    r = client.get("/apk", headers=entetes)
    assert r.status_code == 404
    assert "envoyer-apk" in r.json()["detail"]


def test_apk_est_servi_avec_le_bon_type_et_un_nom_de_fichier(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    contenu = b"PK\x03\x04 ceci est un apk"
    _deposer(tmp_path, contenu=contenu, infos=INFOS)
    _, client = _client(tmp_path, monkeypatch)

    r = client.get("/apk", headers=entetes)
    assert r.status_code == 200
    assert r.content == contenu
    assert r.headers["content-type"] == "application/vnd.android.package-archive"
    # Le nom porte la version : deux APK téléchargés ne se confondent pas dans
    # le dossier de téléchargements du téléphone.
    assert "phototheque-1.0.apk" in r.headers["content-disposition"]


def test_apk_sans_version_garde_un_nom_utilisable(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    _deposer(tmp_path, contenu=b"PK\x03\x04")
    _, client = _client(tmp_path, monkeypatch)
    r = client.get("/apk", headers=entetes)
    assert r.status_code == 200
    assert ".apk" in r.headers["content-disposition"]


def test_apk_exige_le_mot_de_passe(tmp_path, monkeypatch):
    """Le binaire n'est pas public : le NUC ne distribue rien au tout-venant."""
    _avec_admin(tmp_path, monkeypatch)
    _deposer(tmp_path)
    _, client = _client(tmp_path, monkeypatch)
    r = client.get("/apk")
    assert r.status_code == 401
    assert "Basic" in r.headers.get("WWW-Authenticate", "")


# ------------------------------------------------------- la page d'admin

DISQUE = {"total": 1000, "utilise": 700, "libre": 300, "pourcentage_utilise": 70}
MEDIA = {"photos": 1, "videos": 1}


def test_la_page_d_admin_propose_le_telechargement(tmp_path):
    html = web.admin_html([], DISQUE, MEDIA, apk={
        "version": "1.0", "version_code": 3, "octets": 25380462,
        "construit_le": "2026-09-21T11:04:00", "sha256": "a" * 64})
    assert "/apk" in html
    assert "1.0" in html


def test_la_page_d_admin_dit_quand_aucun_apk_n_est_depose(tmp_path):
    """Le silence serait le pire : on croirait la fonction cassée."""
    html = web.admin_html([], DISQUE, MEDIA, apk=None)
    assert "envoyer-apk" in html
    assert 'href="/apk"' not in html


def test_la_page_d_admin_marche_sans_argument_apk():
    """Compatibilité : l'appel historique à trois arguments ne casse pas."""
    assert "phototheque" in web.admin_html([], DISQUE, MEDIA)
