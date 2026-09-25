"""Tests du modèle de page : niveaux, libellés, pagination, filtres."""
from datetime import date
from urllib.parse import parse_qs, urlparse

from phototheque import galerie_index as gi
from phototheque import galerie_vue as gv
from phototheque.classement import classer

BIB = "/bib"


def _m(e, rel, dp=None):
    ch = f"{BIB}/{rel}"
    return gi.Media(e, ch, 1, classer(ch, dp, BIB))


def _index():
    return gi.Index([
        _m("a", "Photos/2023/06 JUIN/IMG_1.jpg", "2023-06-19"),
        _m("b", "Photos/2023/06 JUIN/IMG_2.jpg"),
        _m("c", "Photos/2022/01 JANVIER/IMG_3.jpg"),
        _m("d", "Documents/logo.png"),
    ])


def test_accueil_liste_les_annees_et_le_rayon_sans_date():
    v = gv.construire_vue(_index(), gi.Filtres())
    assert [(lib, n) for lib, _, n in v.blocs] == [("2023", 2), ("2022", 1), ("Sans date", 1)]
    assert v.groupes == []


def test_une_annee_liste_ses_mois_en_francais():
    v = gv.construire_vue(_index(), gi.Filtres(), annee=2023)
    assert [lib for lib, _, _ in v.blocs] == ["Juin"]
    assert [lib for lib, _ in v.fil] == ["Toutes les années", "2023"]


def test_un_mois_avec_des_jours_connus_montre_le_niveau_jours_et_la_grille():
    v = gv.construire_vue(_index(), gi.Filtres(), annee=2023, mois=6)
    assert [lib for lib, _, _ in v.blocs] == ["lundi 19", "Jour inconnu"]
    assert [(titre, [m.empreinte for m in ms]) for titre, ms in v.groupes] == \
        [("lundi 19", ["a"]), ("Jour inconnu", ["b"])]


def test_un_mois_sans_aucun_jour_connu_affiche_sa_grille_directement():
    # Spec §5 : dégradation naturelle, sans message d'erreur.
    v = gv.construire_vue(_index(), gi.Filtres(), annee=2022, mois=1)
    assert v.blocs == []
    assert [m.empreinte for _, ms in v.groupes for m in ms] == ["c"]


def test_le_rayon_sans_date_affiche_sa_grille():
    v = gv.construire_vue(_index(), gi.Filtres(), annee=gi.SANS)
    assert [m.empreinte for _, ms in v.groupes for m in ms] == ["d"]


def test_la_pagination_garde_les_filtres():
    # Point de vigilance n° 5 : le mariage compte 3 158 photos dans un mois.
    ix = gi.Index([_m(f"{i:064x}", f"Photos/2014-10 - Mariage/AK-{i:04d}.jpg")
                   for i in range(300)])
    f = gi.Filtres(type="photo", origine="appareil")
    v = gv.construire_vue(ix, f, annee=2014, mois=10, page=2)
    assert (v.page, v.pages, v.total) == (2, 3, 300)
    assert sum(len(ms) for _, ms in v.groupes) == gv.TAILLE_PAGE
    q = parse_qs(urlparse(v.suivante).query)
    assert q == {"annee": ["2014"], "mois": ["10"], "type": ["photo"],
                 "origine": ["appareil"], "page": ["3"]}
    assert "page" not in parse_qs(urlparse(v.precedente).query), "page 1 = sans « page »"


def test_une_page_hors_limites_est_ramenee_dans_les_bornes():
    v = gv.construire_vue(_index(), gi.Filtres(), annee=2023, mois=6, page=99)
    assert v.page == 1 and v.suivante is None


def test_lire_filtres_ignore_les_valeurs_inconnues():
    f, msg = gv.lire_filtres("pas-une-date", "", "gif", "martien")
    assert f == gi.Filtres() and msg is None


def test_lire_filtres_inverse_des_dates_a_l_envers_et_le_dit():
    f, msg = gv.lire_filtres("2023-12-31", "2023-01-01", "", "")
    assert (f.du, f.au) == (date(2023, 1, 1), date(2023, 12, 31))
    assert "inversées" in msg


def test_lire_niveau():
    assert (gv.lire_niveau(""), gv.lire_niveau("sans"), gv.lire_niveau("2023"),
            gv.lire_niveau("x")) == (None, gi.SANS, 2023, None)


def test_un_jour_impossible_garde_son_numero():
    assert gv.libelle_jour(2023, 2, 30) == "30"


def test_la_position_est_gardee_pour_le_formulaire():
    v = gv.construire_vue(_index(), gi.Filtres(), annee=2023, mois=6)
    assert v.position == {"annee": "2023", "mois": "6"}
