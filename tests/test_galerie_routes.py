"""Routes de service de la galerie : authentification, sûreté, Range."""
import base64
import importlib
import time

import pytest
from fastapi.testclient import TestClient

from mediasort.catalog import Catalog

E_PHOTO, E_VIDEO, E_HORS, E_PARTI = "1" * 64, "2" * 64, "3" * 64, "4" * 64


def _client(tmp_path, monkeypatch):
    from phototheque import adminauth
    (tmp_path / "admin").write_text(adminauth.empreinte("secret", iterations=1000))
    for cle, valeur in {
        "LIBRARY_DIR": tmp_path / "Famille", "CATALOG_DB": tmp_path / "cat.db",
        "INCOMING_DIR": tmp_path / "incoming", "DEVICES_DB": tmp_path / "dev.db",
        "JOURNAL_DB": tmp_path / "j.db", "GALERIE_DB": tmp_path / "g.db",
        "VIGNETTES_DIR": tmp_path / "vign", "ADMIN_FILE": tmp_path / "admin",
        "APK_FILE": tmp_path / "app.apk",
    }.items():
        monkeypatch.setenv(cle, str(valeur))
    bib = tmp_path / "Famille"
    (bib / "Photos/2023/06 JUIN").mkdir(parents=True)
    (bib / "Videos/2023/06 JUIN").mkdir(parents=True)
    (bib / "Photos/2023/06 JUIN/IMG_1.jpg").write_bytes(b"\xff\xd8photo")
    video = bib / "Videos/2023/06 JUIN/VID_1.mp4"
    with open(video, "wb") as f:              # 1 Gio creux : n'occupe pas le disque
        f.truncate(1024 ** 3)
    secret = tmp_path / "secret.txt"
    secret.write_text("ne doit jamais sortir")
    cat = Catalog(tmp_path / "cat.db")
    cat.add_media(E_PHOTO, 7, str(bib / "Photos/2023/06 JUIN/IMG_1.jpg"), None, "seed")
    cat.add_media(E_VIDEO, 1024 ** 3, str(video), None, "seed")
    cat.add_media(E_HORS, 1, str(secret), None, "seed")                     # hors bibliothèque
    cat.add_media(E_PARTI, 1, str(bib / "Photos/2023/06 JUIN/parti.jpg"), None, "seed")
    cat.close()
    import phototheque.config as c
    importlib.reload(c)
    import phototheque.app as a
    importlib.reload(a)
    jeton = base64.b64encode(b"admin:secret").decode()
    return a, TestClient(a.app), {"Authorization": f"Basic {jeton}"}


@pytest.mark.parametrize("adresse", [f"/galerie/vignette/{E_PHOTO}",
                                     f"/galerie/original/{E_PHOTO}",
                                     f"/galerie/moyenne/{E_PHOTO}"])
def test_les_routes_de_service_exigent_une_authentification(adresse, tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    assert client.get(adresse).status_code == 401


def test_un_jeton_d_appareil_suffit(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Téléphone")
    r = client.get(f"/galerie/original/{E_PHOTO}", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200


def test_un_faux_jeton_d_appareil_est_refuse(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/original/{E_PHOTO}", headers={"Authorization": "Bearer faux"})
    assert r.status_code == 401


def test_original_sert_le_fichier(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/original/{E_PHOTO}", headers=adm)
    assert r.status_code == 200 and r.content == b"\xff\xd8photo"


@pytest.mark.parametrize("forgee", ["../../etc/passwd", "5" * 64, "A" * 64, "%2e%2e%2fsecret"])
def test_une_empreinte_forgee_ou_inconnue_repond_404(forgee, tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    assert client.get(f"/galerie/original/{forgee}", headers=adm).status_code == 404


def test_un_chemin_de_catalogue_hors_bibliotheque_n_est_jamais_ouvert(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/original/{E_HORS}", headers=adm)
    assert r.status_code == 404 and b"jamais sortir" not in r.content


def test_original_d_un_fichier_disparu_repond_404(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    assert client.get(f"/galerie/original/{E_PARTI}", headers=adm).status_code == 404


def test_une_requete_range_sur_une_grande_video_ne_lit_pas_le_fichier(tmp_path, monkeypatch):
    # Spec §9.6, leçon de l'issue #21 : 1 Gio lu en mémoire prendrait des
    # secondes et 1 Gio de RAM ; une réponse partielle n'en lit que 1 Kio.
    a, client, adm = _client(tmp_path, monkeypatch)
    debut = time.monotonic()
    r = client.get(f"/galerie/original/{E_VIDEO}", headers={**adm, "Range": "bytes=0-1023"})
    assert r.status_code == 206
    assert len(r.content) == 1024
    assert r.headers["content-range"] == f"bytes 0-1023/{1024 ** 3}"
    assert time.monotonic() - debut < 2


def test_vignette_absente_donne_l_image_de_remplacement(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/vignette/{E_PHOTO}", headers=adm)
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")


def test_vignette_presente_est_servie_en_webp(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    from phototheque.vignettes import chemin_vignette
    p = chemin_vignette(tmp_path / "vign", E_PHOTO)
    p.parent.mkdir(parents=True)
    p.write_bytes(b"RIFF....WEBP")
    r = client.get(f"/galerie/vignette/{E_PHOTO}", headers=adm)
    assert r.headers["content-type"] == "image/webp" and r.content == b"RIFF....WEBP"


def test_moyenne_d_une_video_redirige_vers_l_original(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/moyenne/{E_VIDEO}", headers=adm, follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == f"/galerie/original/{E_VIDEO}"


def test_moyenne_ratee_redirige_vers_l_original(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    def rate(*args, **kw):
        raise a.fabrique.ErreurVignette("ffmpeg (moyenne) : Invalid data")
    monkeypatch.setattr(a.fabrique, "fabriquer_moyenne", rate)
    monkeypatch.setattr(a.fabrique, "lire_metadonnees", lambda chemins: {})
    r = client.get(f"/galerie/moyenne/{E_PHOTO}", headers=adm, follow_redirects=False)
    assert r.status_code == 307


def test_la_documentation_reste_fermee(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    for chemin in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(chemin, headers=adm).status_code == 404


# --- pages -----------------------------------------------------------------

def test_l_accueil_est_la_galerie_et_liste_les_annees(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    from phototheque import galerie_index
    galerie_index.vider_cache()
    r = client.get("/", headers=adm)
    assert r.status_code == 200
    assert "2023" in r.text and 'href="/?annee=2023"' in r.text
    assert 'href="/admin"' in r.text


def test_l_accueil_exige_une_authentification(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    assert client.get("/").status_code == 401


def test_un_mois_affiche_sa_grille_de_vignettes(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    from phototheque import galerie_index
    galerie_index.vider_cache()
    r = client.get("/?annee=2023&mois=6", headers=adm)
    assert f'src="/galerie/vignette/{E_PHOTO}"' in r.text
    assert f'href="/galerie/media/{E_PHOTO}"' in r.text


def test_les_filtres_se_retrouvent_dans_le_formulaire(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get("/?type=video&du=2023-01-01", headers=adm)
    assert 'value="2023-01-01"' in r.text
    assert '<option value="video" selected>' in r.text


def test_un_mois_garde_la_position_dans_le_formulaire(tmp_path, monkeypatch):
    # Etape 5 de la tache 8 : le formulaire doit recoller la position
    # courante (annee/mois/jour) en champs caches, sinon changer un filtre
    # ramenerait a l'accueil (issue #31).
    a, client, adm = _client(tmp_path, monkeypatch)
    from phototheque import galerie_index
    galerie_index.vider_cache()
    r = client.get("/?annee=2023&mois=6", headers=adm)
    assert 'name="annee" value="2023"' in r.text


def test_page_media_photo(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/media/{E_PHOTO}", headers=adm)
    assert f'src="/galerie/moyenne/{E_PHOTO}"' in r.text


def test_page_media_video_propose_le_telechargement_et_le_dit(tmp_path, monkeypatch):
    # Spec §6 : pas de transcodage ; on propose le téléchargement, et on le dit.
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/media/{E_VIDEO}", headers=adm)
    assert "<video" in r.text and f'src="/galerie/original/{E_VIDEO}"' in r.text
    assert "download" in r.text and "télécharger" in r.text.lower()


def test_page_media_inconnue_repond_404(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    assert client.get(f"/galerie/media/{'9' * 64}", headers=adm).status_code == 404


def test_un_nom_piege_est_echappe_partout(tmp_path, monkeypatch):
    # Point de vigilance n° 1 : « A&K », « Les Bouchons d'Aur » existent sur le NUC.
    a, client, adm = _client(tmp_path, monkeypatch)
    nom = "L'été & <moi>.jpg"
    p = tmp_path / "Famille/Photos/2023/06 JUIN" / nom
    p.write_bytes(b"\xff\xd8")
    e = "6" * 64
    cat = Catalog(tmp_path / "cat.db")
    cat.add_media(e, 2, str(p), None, "seed")
    cat.close()
    from phototheque import galerie_index
    galerie_index.vider_cache()
    for adresse in ("/?annee=2023&mois=6", f"/galerie/media/{e}"):
        texte = client.get(adresse, headers=adm).text
        assert "<moi>" not in texte, adresse
        assert "&lt;moi&gt;" in texte, adresse


def test_l_admin_est_a_son_adresse_et_montre_le_recensement(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    from phototheque.vignettes import Vignettes
    base = Vignettes(tmp_path / "g.db")
    base.enregistrer_faite(E_PHOTO, 400, 300, "photo")
    base.enregistrer_erreur(E_VIDEO, "x")
    base.close()
    r = client.get("/admin", headers=adm)
    assert r.status_code == 200
    assert "Galerie" in r.text and "1 vignette" in r.text and "1 en échec" in r.text
