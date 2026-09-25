"""Tests de l'index galerie : filtres, comptes, sélection, cache."""
import os
import sqlite3
from datetime import date

from mediasort.catalog import Catalog
from phototheque import galerie_index as gi
from phototheque.classement import classer

BIB = "/bib"


def _m(empreinte, rel, date_prise=None, taille=1):
    ch = f"{BIB}/{rel}"
    return gi.Media(empreinte, ch, taille, classer(ch, date_prise, BIB))


def _index():
    return gi.Index([
        _m("a", "Photos/2023/06 JUIN/IMG_1.jpg", "2023-06-21"),
        _m("b", "Photos/2023/06 JUIN/IMG_2.jpg", "2023-06-15"),
        _m("c", "Photos/2023/06 JUIN/IMG_3.jpg"),                 # jour inconnu
        _m("d", "Videos/2023/07 JUILLET/VID_1.mp4"),
        _m("e", "WhatsApp/Photos/2022/01 JANVIER/IMG-1.jpg"),
        _m("f", "Documents/x/logo.png"),                          # sans date
    ])


def test_compter_les_annees_du_plus_recent_au_plus_ancien_puis_sans_date():
    assert _index().compter_annees(gi.Filtres()) == [(2023, 4), (2022, 1), (gi.SANS, 1)]


def test_compter_les_mois_d_une_annee():
    assert _index().compter_mois(gi.Filtres(), 2023) == [(7, 1), (6, 3)]


def test_compter_les_jours_met_le_jour_inconnu_en_dernier():
    assert _index().compter_jours(gi.Filtres(), 2023, 6) == [(15, 1), (21, 1), (gi.SANS, 1)]


def test_un_media_sans_date_prise_reste_dans_son_mois():
    # Spec §9.2 : c'est le cas de 98 % de la bibliothèque, pas un cas dégradé.
    noms = [m.empreinte for m in _index().selectionner(gi.Filtres(), 2023, 6)]
    assert noms == ["b", "a", "c"], "jour connu d'abord (15 puis 21), inconnu ensuite"


def test_selectionner_le_rayon_sans_date():
    assert [m.empreinte for m in _index().selectionner(gi.Filtres(), gi.SANS)] == ["f"]


def test_filtre_type():
    assert [m.empreinte for m in _index().filtrer(gi.Filtres(type="video"))] == ["d"]


def test_filtre_origine():
    assert [m.empreinte for m in _index().filtrer(gi.Filtres(origine="whatsapp"))] == ["e"]


def test_filtre_dates_sur_un_jour_connu():
    f = gi.Filtres(du=date(2023, 6, 16), au=date(2023, 6, 30))
    assert "a" in [m.empreinte for m in _index().filtrer(f)]
    assert "b" not in [m.empreinte for m in _index().filtrer(f)]


def test_filtre_dates_garde_un_media_dont_seul_le_mois_est_connu():
    # « Reproposer plutôt que sauter » : juin chevauche l'intervalle, on le garde.
    f = gi.Filtres(du=date(2023, 6, 16), au=date(2023, 6, 30))
    assert "c" in [m.empreinte for m in _index().filtrer(f)]


def test_filtre_dates_ecarte_le_sans_date():
    f = gi.Filtres(du=date(2000, 1, 1))
    assert "f" not in [m.empreinte for m in _index().filtrer(f)]


def test_une_date_de_prise_impossible_ne_plante_pas_le_filtre():
    ix = gi.Index([_m("z", "Photos/2023/02 FEVRIER/a.jpg", "2023-02-30")])
    assert ix.filtrer(gi.Filtres(du=date(2023, 2, 1), au=date(2023, 2, 28))) != []


def _catalogue(tmp_path, lignes):
    cat = Catalog(tmp_path / "cat.db")
    for e, ch, dp in lignes:
        cat.add_media(e, 10, ch, dp, "seed" if dp is None else "metadata")
    cat.close()
    return tmp_path / "cat.db"


def test_depuis_catalogue_ignore_ce_qui_n_est_pas_un_media(tmp_path):
    db = _catalogue(tmp_path, [
        ("a" * 64, f"{BIB}/Photos/2023/06 JUIN/IMG_1.jpg", None),
        ("b" * 64, f"{BIB}/Documents/plaquette.pdf", None),
    ])
    ix = gi.Index.depuis_catalogue(db, BIB)
    assert [m.empreinte for m in ix.tous()] == ["a" * 64]
    assert ix.trouver("a" * 64).c.annee == 2023


def test_depuis_catalogue_ignore_une_empreinte_mal_formee(tmp_path):
    # Défense en profondeur : l'empreinte finit dans des href et des src.
    db = _catalogue(tmp_path, [
        ("a" * 64, f"{BIB}/Photos/2023/06 JUIN/IMG_1.jpg", None),
        ('"><script>x</script>', f"{BIB}/Photos/2023/06 JUIN/IMG_2.jpg", None),
        ("A" * 64, f"{BIB}/Photos/2023/06 JUIN/IMG_3.jpg", None),
    ])
    ix = gi.Index.depuis_catalogue(db, BIB)
    assert [m.empreinte for m in ix.tous()] == ["a" * 64]


def test_le_cache_se_reconstruit_quand_le_catalogue_change(tmp_path):
    gi.vider_cache()
    db = _catalogue(tmp_path, [("a" * 64, f"{BIB}/Photos/2023/06 JUIN/1.jpg", None)])
    horloge = [1000.0]
    assert len(gi.index_courant(db, BIB, maintenant=lambda: horloge[0])) == 1
    cat = Catalog(db)
    cat.add_media("b" * 64, 10, f"{BIB}/Photos/2023/06 JUIN/2.jpg", None, "seed")
    cat.close()
    st = os.stat(db)
    os.utime(db, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    horloge[0] += 5                       # trop tôt : on garde l'ancien index
    assert len(gi.index_courant(db, BIB, maintenant=lambda: horloge[0])) == 1
    horloge[0] += 60                      # délai passé : on reconstruit
    assert len(gi.index_courant(db, BIB, maintenant=lambda: horloge[0])) == 2


def test_catalogue_absent_donne_un_index_vide(tmp_path):
    gi.vider_cache()
    assert len(gi.index_courant(tmp_path / "absent.db", BIB)) == 0
