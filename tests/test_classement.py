"""Tests du classement galerie : type, origine et date déduits du chemin."""
from phototheque.classement import APPAREIL, AUTRE, WHATSAPP, classer

BIB = "/media/izquierdo/Famille"


def _c(rel, date_prise=None):
    return classer(f"{BIB}/{rel}", date_prise, BIB)


def test_chemin_canonique_photo():
    c = _c("Photos/2013/05 MAI/IMG_1.jpg")
    assert (c.type, c.origine, c.annee, c.mois, c.jour, c.source) == \
        ("photo", APPAREIL, 2013, 5, None, "chemin")


def test_chemin_canonique_video_whatsapp():
    c = _c("WhatsApp/Videos/2023/06 JUIN/VID-20230625-WA0001.mp4")
    assert (c.type, c.origine, c.annee, c.mois) == ("video", WHATSAPP, 2023, 6)


def test_mois_ecrit_avec_deux_espaces():
    # Réel : « WhatsApp/Photos/2013/10  OCTOBRE/ » existe sur le NUC.
    assert _c("WhatsApp/Photos/2013/10  OCTOBRE/IMG-1.jpg").mois == 10


def test_dossier_d_evenement_date_dans_son_nom():
    c = _c("Photos/2014-10 - A&K - Mariage/LM Noir&Blanc Facebook/AK-2377.jpg")
    assert (c.annee, c.mois, c.origine) == (2014, 10, APPAREIL)


def test_annee_seule_dans_le_nom_d_un_dossier():
    c = _c("Photos/2003 - Photos Michèle/mon album 142.jpg")
    assert (c.annee, c.mois) == (2003, None)


def test_mois_nomme_apres_une_annee():
    assert (_c("Photos/2022/02 - CANARIAS/IMG_1.jpg").annee,
            _c("Photos/2022/02 - CANARIAS/IMG_1.jpg").mois) == (2022, 2)


def test_sous_dossier_dans_un_mois():
    c = _c("Photos/2017/06 JUIN/Mariage SetA/0246Flo.JPG")
    assert (c.annee, c.mois) == (2017, 6)


def test_annee_sans_mois():
    c = _c("Videos/2020/VID_20200806_164934.mp4")
    assert (c.annee, c.mois, c.type) == (2020, None, "video")


def test_dossier_sans_date_va_dans_sans_date_origine_autre():
    c = _c("Documents/LA CIGALIERE/Divers/jpd firma.jpg")
    assert (c.annee, c.mois, c.jour, c.source, c.origine) == \
        (None, None, None, "aucune", AUTRE)


def test_whatsapp_meme_sous_unsorted():
    assert _c("unsorted/WhatsApp/Media/x/VID-20231105-WA0000.mp4").origine == WHATSAPP


def test_la_date_de_prise_prime_sur_le_chemin():
    c = _c("Photos/2014-10 - A&K - Mariage/AK-1.jpg", date_prise="2014-10-18")
    assert (c.annee, c.mois, c.jour, c.source) == (2014, 10, 18, "date_prise")


def test_une_date_de_prise_illisible_retombe_sur_le_chemin():
    c = _c("Photos/2013/05 MAI/IMG_1.jpg", date_prise="0000-00-00")
    assert (c.annee, c.mois, c.jour, c.source) == (2013, 5, None, "chemin")


def test_extension_non_geree_n_est_pas_un_media():
    assert _c("Documents/plaquette.pdf") is None


def test_un_reste_appledouble_n_est_pas_un_media():
    # Point de vigilance n° 4 : « ._Combat Philou….mp4 » existe sur le NUC.
    assert _c("Videos/2018-10 - Ken competition/._Combat.mp4") is None


def test_extension_en_majuscules():
    assert _c("Videos/2015/09 SEPTEMBRE/HDV_0495.MP4").type == "video"


def test_chemin_hors_bibliotheque_reste_classable():
    c = classer("/ailleurs/Photos/2019/01 JANVIER/a.jpg", None, BIB)
    assert (c.annee, c.mois) == (2019, 1)


# --- règle du mainteneur (25/09) : l'EXIF prime, sauf écart d'un an ou plus ---

def test_exif_proche_du_dossier_prime():
    # Appareil un peu en avance ou en retard : la vraie date l'emporte.
    c = _c("Photos/2014-10 - A&K - Mariage/AK-1.jpg", date_prise="2014-09-12")
    assert (c.annee, c.mois, c.jour, c.source) == (2014, 9, 12, "date_prise")


def test_exif_a_plus_d_un_an_du_dossier_cede_au_dossier():
    # Appareil remis à zéro après un changement de pile : le dossier classé à
    # la main dit mieux la vérité.
    c = _c("Photos/2014-10 - A&K - Mariage/AK-1.jpg", date_prise="2009-01-01")
    assert (c.annee, c.mois, c.jour, c.source) == (2014, 10, None, "chemin")


def test_ecart_mesure_depuis_la_fin_du_mois_du_dossier():
    # Dossier = octobre 2014 (1er au 31). 30/10/2015 : 364 jours après le
    # 31/10/2014, l'EXIF prime ; 31/10/2015 : 365 jours, le dossier prime.
    dossier = "Photos/2014/10 OCTOBRE/IMG.jpg"
    assert _c(dossier, date_prise="2015-10-30").source == "date_prise"
    assert _c(dossier, date_prise="2015-10-31").source == "chemin"


def test_ecart_mesure_depuis_le_debut_du_mois_du_dossier():
    dossier = "Photos/2014/10 OCTOBRE/IMG.jpg"
    assert _c(dossier, date_prise="2013-10-02").source == "date_prise"   # 364 j
    assert _c(dossier, date_prise="2013-10-01").source == "chemin"       # 365 j


def test_dossier_date_a_l_annee_se_mesure_sur_toute_l_annee():
    dossier = "Photos/2003 - Photos Michèle/mon album 142.jpg"
    assert _c(dossier, date_prise="2003-06-01").source == "date_prise"
    c = _c(dossier, date_prise="2010-06-01")
    assert (c.annee, c.mois, c.source) == (2003, None, "chemin")


def test_sans_date_de_dossier_l_exif_prime_toujours():
    c = _c("Photos/Divers/AK 2.jpg", date_prise="1999-05-04")
    assert (c.annee, c.mois, c.jour, c.source) == (1999, 5, 4, "date_prise")


def test_une_date_de_prise_impossible_se_compare_a_son_mois():
    # « 30 février » d'un appareil déréglé : ni plantage ni rejet sans raison.
    c = _c("Photos/2023/02 FEVRIER/a.jpg", date_prise="2023-02-30")
    assert (c.annee, c.mois, c.source) == (2023, 2, "date_prise")
