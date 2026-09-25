"""Tests du recensement : reprise, erreurs isolées, dates, pause, verrou."""
import os
import sqlite3
import time
from pathlib import Path

from mediasort.catalog import Catalog
from phototheque import recensement as r
from phototheque.fabrique import ErreurVignette
from phototheque.vignettes import Vignettes, chemin_vignette


def _bib(tmp_path, fichiers):
    """Crée des fichiers sous une bibliothèque et les inscrit au catalogue."""
    bib = tmp_path / "Famille"
    cat = Catalog(tmp_path / "cat.db")
    empreintes = []
    for i, (rel, date_prise) in enumerate(fichiers):
        p = bib / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        e = f"{i:064x}"
        cat.add_media(e, 1, str(p), date_prise, "seed" if date_prise is None else "metadata")
        empreintes.append(e)
    cat.close()
    return bib, tmp_path / "cat.db", empreintes


def _faux_fabriquer(echecs=()):
    def fabriquer(chemin, type_, meta, cible, executer=None):
        if Path(chemin).name in echecs:
            raise ErreurVignette("ffmpeg (photo) : Invalid data found")
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(b"webp")
        return 400, 300, "photo"
    return fabriquer


def _passe(tmp_path, bib, db, **kw):
    kw.setdefault("lire", lambda chemins: {})
    kw.setdefault("fabriquer", _faux_fabriquer())
    return r.Passe(db, Vignettes(tmp_path / "g.db"), tmp_path / "vign", bib,
                   tmp_path / "incoming", dormir=lambda s: None, **kw)


def _date_prise(db, e):
    cx = sqlite3.connect(db)
    try:
        return cx.execute("SELECT date_prise, source_date FROM medias WHERE empreinte=?",
                          (e,)).fetchone()
    finally:
        cx.close()


def test_la_passe_fait_les_vignettes(tmp_path):
    bib, db, (e,) = _bib(tmp_path, [("Photos/2023/06 JUIN/IMG_1.jpg", None)])
    assert _passe(tmp_path, bib, db).executer()["faites"] == 1
    assert chemin_vignette(tmp_path / "vign", e).exists()


def test_le_recensement_reprend_ou_il_s_est_arrete(tmp_path):
    bib, db, _ = _bib(tmp_path, [(f"Photos/2023/06 JUIN/IMG_{i}.jpg", None) for i in range(5)])
    assert _passe(tmp_path, bib, db).executer(limite=2)["faites"] == 2
    vus = []
    def fabriquer(chemin, type_, meta, cible, executer=None):
        vus.append(chemin)
        return _faux_fabriquer()(chemin, type_, meta, cible)
    assert _passe(tmp_path, bib, db, fabriquer=fabriquer).executer()["faites"] == 3
    assert len(vus) == 3, "les deux premières ne sont pas refaites"


def test_une_vignette_en_echec_n_arrete_pas_la_passe(tmp_path):
    bib, db, (e1, e2) = _bib(tmp_path, [("Photos/2023/06 JUIN/casse.jpg", None),
                                        ("Photos/2023/06 JUIN/bon.jpg", None)])
    bilan = _passe(tmp_path, bib, db, fabriquer=_faux_fabriquer({"casse.jpg"})).executer()
    assert (bilan["faites"], bilan["erreurs"]) == (1, 1)
    trace = Vignettes(tmp_path / "g.db").dernieres_erreurs()
    assert trace[0]["empreinte"] == e1 and "Invalid data" in trace[0]["erreur"]


def test_un_fichier_disparu_est_note_et_la_passe_continue(tmp_path):
    # Point de vigilance n° 2 : un dossier curaté déplacé à la main.
    bib, db, (e1, _) = _bib(tmp_path, [("Photos/2023/06 JUIN/parti.jpg", None),
                                       ("Photos/2023/06 JUIN/la.jpg", None)])
    (bib / "Photos/2023/06 JUIN/parti.jpg").unlink()
    bilan = _passe(tmp_path, bib, db).executer()
    assert (bilan["faites"], bilan["erreurs"]) == (1, 1)
    assert "absent" in Vignettes(tmp_path / "g.db").dernieres_erreurs()[0]["erreur"]


def test_les_plus_recents_d_abord(tmp_path):
    bib, db, _ = _bib(tmp_path, [("Photos/2013/05 MAI/vieux.jpg", None),
                                 ("Photos/2023/06 JUIN/recent.jpg", None)])
    ordre = [m.nom for m in r.a_traiter(db, Vignettes(tmp_path / "g.db"), bib)]
    assert ordre == ["recent.jpg", "vieux.jpg"]


def test_la_recolte_ecrit_date_prise_depuis_les_metadonnees(tmp_path):
    bib, db, (e,) = _bib(tmp_path, [("Photos/2019/05 MAI/IMG_1.jpg", None)])
    chemin = str(bib / "Photos/2019/05 MAI/IMG_1.jpg")
    lire = lambda chemins: {chemin: {"DateTimeOriginal": "2019:05:04 10:00:00"}}
    assert _passe(tmp_path, bib, db, lire=lire).executer()["dates"] == 1
    assert _date_prise(db, e) == ("2019-05-04", "metadata")


def test_la_recolte_retombe_sur_le_nom_du_fichier(tmp_path):
    bib, db, (e,) = _bib(tmp_path, [("WhatsApp/Photos/2023/06 JUIN/IMG-20230625-WA0025.jpg", None)])
    _passe(tmp_path, bib, db).executer()
    assert _date_prise(db, e) == ("2023-06-25", "filename")


def test_une_date_nulle_ne_s_ecrit_pas(tmp_path):
    # Point de vigilance n° 3 : « 0000:00:00 » des vieux appareils.
    bib, db, (e,) = _bib(tmp_path, [("Photos/Divers/AK 2.jpg", None)])
    chemin = str(bib / "Photos/Divers/AK 2.jpg")
    lire = lambda chemins: {chemin: {"DateTimeOriginal": "0000:00:00 00:00:00"}}
    _passe(tmp_path, bib, db, lire=lire).executer()
    assert _date_prise(db, e) == (None, "seed")


def test_la_recolte_n_ecrase_jamais_une_date_connue(tmp_path):
    bib, db, (e,) = _bib(tmp_path, [("Photos/2019/05 MAI/IMG_1.jpg", "2019-05-01")])
    chemin = str(bib / "Photos/2019/05 MAI/IMG_1.jpg")
    lire = lambda chemins: {chemin: {"DateTimeOriginal": "2019:05:04 10:00:00"}}
    _passe(tmp_path, bib, db, lire=lire).executer()
    assert _date_prise(db, e) == ("2019-05-01", "metadata")


def test_ecrire_dates_ne_touche_que_les_trous(tmp_path):
    bib, db, (e1, e2) = _bib(tmp_path, [("Photos/a.jpg", None), ("Photos/b.jpg", "2001-01-01")])
    n = r.ecrire_dates(db, [(e1, "2020-02-02", "metadata"), (e2, "2020-02-02", "metadata")])
    assert n == 1 and _date_prise(db, e2) == ("2001-01-01", "metadata")


def test_synchro_en_cours_voit_une_session_recente(tmp_path):
    incoming = tmp_path / "incoming"
    session = incoming / ("c" * 32)
    session.mkdir(parents=True)
    (session / "a.jpg.partiel").write_bytes(b"x")
    assert r.synchro_en_cours(incoming)
    assert not r.synchro_en_cours(incoming, maintenant=lambda: time.time() + 3600)


def test_synchro_en_cours_ignore_la_quarantaine(tmp_path):
    incoming = tmp_path / "incoming"
    (incoming / "_echecs" / "x").mkdir(parents=True)
    assert not r.synchro_en_cours(incoming)


def test_la_passe_attend_la_fin_d_une_synchro(tmp_path, monkeypatch):
    bib, db, _ = _bib(tmp_path, [("Photos/2023/06 JUIN/IMG_1.jpg", None)])
    reponses = iter([True, True, False])
    monkeypatch.setattr(r, "synchro_en_cours", lambda *a, **k: next(reponses))
    siestes = []
    p = r.Passe(db, Vignettes(tmp_path / "g.db"), tmp_path / "vign", bib, tmp_path / "in",
                lire=lambda c: {}, fabriquer=_faux_fabriquer(), dormir=siestes.append)
    assert p.executer()["faites"] == 1
    assert len(siestes) == 2


def test_un_arret_demande_sort_proprement(tmp_path):
    bib, db, _ = _bib(tmp_path, [(f"Photos/2023/06 JUIN/{i}.jpg", None) for i in range(3)])
    p = _passe(tmp_path, bib, db, doit_s_arreter=lambda: True)
    assert p.executer()["faites"] == 0


def test_ecrire_dates_reprend_apres_un_verrou_transitoire(tmp_path, monkeypatch):
    # Le catalogue est partage avec le trieur (base a journal de retour
    # arriere, pas WAL) : un verrou concurrent peut depasser le delai de
    # connexion. Deux echecs transitoires ne doivent pas faire perdre la date.
    bib, db, (e,) = _bib(tmp_path, [("Photos/2019/05 MAI/IMG_1.jpg", None)])
    chemin = str(bib / "Photos/2019/05 MAI/IMG_1.jpg")
    lire = lambda chemins: {chemin: {"DateTimeOriginal": "2019:05:04 10:00:00"}}
    vrai_ecrire_dates = r.ecrire_dates
    effets = iter([sqlite3.OperationalError("database is locked"),
                   sqlite3.OperationalError("database is locked"),
                   None])
    def faux(catalog_db, dates):
        effet = next(effets)
        if effet is not None:
            raise effet
        return vrai_ecrire_dates(catalog_db, dates)
    monkeypatch.setattr(r, "ecrire_dates", faux)
    siestes = []
    p = r.Passe(db, Vignettes(tmp_path / "g.db"), tmp_path / "vign", bib, tmp_path / "incoming",
                lire=lire, fabriquer=_faux_fabriquer(), dormir=siestes.append)
    bilan = p.executer()
    assert bilan == {"faites": 1, "erreurs": 0, "dates": 1}
    assert len(siestes) == 2
    assert Vignettes(tmp_path / "g.db").dernieres_erreurs() == []
    assert _date_prise(db, e) == ("2019-05-04", "metadata")


def test_ecrire_dates_qui_echoue_toujours_bascule_en_erreur_et_continue(tmp_path, monkeypatch):
    # Trois echecs d'affilee : la date de ce lot est perdue pour cette passe,
    # mais le media (deja enregistre 'faite') ne doit pas rester silencieusement
    # ainsi pour toujours — il repasse en erreur pour etre repris par
    # --reessayer-erreurs — et le lot SUIVANT doit quand meme etre traite.
    monkeypatch.setattr(r, "LOT", 1)
    bib, db, (e1, e2) = _bib(tmp_path, [("Photos/2023/06 JUIN/a.jpg", None),
                                        ("Photos/2023/06 JUIN/b.jpg", None)])
    chemin1 = str(bib / "Photos/2023/06 JUIN/a.jpg")
    chemin2 = str(bib / "Photos/2023/06 JUIN/b.jpg")
    lire = lambda chemins: {
        chemin1: {"DateTimeOriginal": "2023:06:01 10:00:00"},
        chemin2: {"DateTimeOriginal": "2023:06:02 10:00:00"},
    }
    def faux(catalog_db, dates):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(r, "ecrire_dates", faux)
    siestes = []
    p = r.Passe(db, Vignettes(tmp_path / "g.db"), tmp_path / "vign", bib, tmp_path / "incoming",
                lire=lire, fabriquer=_faux_fabriquer(), dormir=siestes.append)
    bilan = p.executer()
    assert bilan == {"faites": 0, "erreurs": 2, "dates": 0}
    erreurs = {t["empreinte"]: t["erreur"] for t in Vignettes(tmp_path / "g.db").dernieres_erreurs()}
    assert set(erreurs) == {e1, e2}
    assert all("date non écrite" in msg for msg in erreurs.values())
    assert _date_prise(db, e1) == (None, "seed")
    assert _date_prise(db, e2) == (None, "seed")


def test_un_seul_recensement_a_la_fois(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib
    import phototheque.config as c
    importlib.reload(c)
    verrou = r._prendre_verrou(tmp_path / "recensement.verrou")
    assert verrou is not None
    assert r._prendre_verrou(tmp_path / "recensement.verrou") is None
    verrou.close()
