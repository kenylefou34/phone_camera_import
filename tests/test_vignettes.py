"""Tests de la table des vignettes (base à part, reprenable)."""
from pathlib import Path

import pytest

from phototheque import vignettes as v

E1, E2 = "a" * 64, "b" * 64


def test_une_vignette_faite_est_retenue_apres_reouverture(tmp_path):
    base = v.Vignettes(tmp_path / "g.db")
    base.enregistrer_faite(E1, 400, 300, "photo")
    base.close()
    assert v.Vignettes(tmp_path / "g.db").traitees() == {E1}


def test_une_erreur_compte_comme_traitee_et_laisse_une_trace(tmp_path):
    base = v.Vignettes(tmp_path / "g.db")
    base.enregistrer_erreur(E2, "ffmpeg : Invalid data found")
    assert base.traitees() == {E2}
    assert base.dernieres_erreurs()[0]["erreur"] == "ffmpeg : Invalid data found"


def test_reussir_apres_une_erreur_efface_l_erreur(tmp_path):
    base = v.Vignettes(tmp_path / "g.db")
    base.enregistrer_erreur(E1, "x")
    base.enregistrer_faite(E1, 160, 120, "exif")
    b = base.bilan()
    assert (b["faites"], b["erreurs"]) == (1, 0)


def test_oublier_les_erreurs_les_remet_en_file(tmp_path):
    base = v.Vignettes(tmp_path / "g.db")
    base.enregistrer_faite(E1, 1, 1, "photo")
    base.enregistrer_erreur(E2, "x")
    assert base.oublier_erreurs() == 1
    assert base.traitees() == {E1}


def test_bilan_d_une_base_vide(tmp_path):
    assert v.Vignettes(tmp_path / "g.db").bilan() == {"faites": 0, "erreurs": 0, "derniere": None}


def test_chemins_des_fichiers_repartis_par_deux_premiers_caracteres(tmp_path):
    assert v.chemin_vignette(tmp_path, E1) == tmp_path / "aa" / f"{E1}.webp"
    assert v.chemin_moyenne(tmp_path, E1) == tmp_path / "moyennes" / "aa" / f"{E1}.webp"


@pytest.mark.parametrize("forgee", ["../../etc/passwd", "A" * 64, "a" * 63, "g" * 64, "",
                                    "a" * 64 + "/../x"])
def test_une_empreinte_forgee_ne_passe_pas_le_motif(forgee):
    assert not v.EMPREINTE.fullmatch(forgee)


def test_les_chemins_refusent_une_empreinte_forgee(tmp_path):
    with pytest.raises(ValueError):
        v.chemin_vignette(tmp_path, "../" + "a" * 61)
