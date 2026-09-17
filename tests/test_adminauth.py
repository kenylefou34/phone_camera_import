"""Tests du mot de passe d'administration (issue #10)."""

from phototheque import adminauth


def test_le_mot_de_passe_n_est_pas_stocke_en_clair():
    enregistre = adminauth.empreinte("correct-cheval-pile-agrafe")
    assert "correct-cheval-pile-agrafe" not in enregistre


def test_format_enregistre():
    """Le format porte ses paramètres : on pourra durcir sans tout casser."""
    enregistre = adminauth.empreinte("secret")
    algo, iterations, sel, empreinte = enregistre.split("$")
    assert algo == "pbkdf2_sha256"
    assert int(iterations) >= 100_000
    assert len(sel) == 32 and len(empreinte) == 64


def test_le_bon_mot_de_passe_est_accepte():
    enregistre = adminauth.empreinte("secret")
    assert adminauth.verifier("secret", enregistre) is True


def test_un_mauvais_mot_de_passe_est_refuse():
    enregistre = adminauth.empreinte("secret")
    assert adminauth.verifier("Secret", enregistre) is False
    assert adminauth.verifier("", enregistre) is False


def test_deux_empreintes_du_meme_mot_de_passe_different():
    """Sel aléatoire : deux installations n'ont pas la même empreinte."""
    assert adminauth.empreinte("secret") != adminauth.empreinte("secret")


def test_un_enregistrement_illisible_refuse_tout():
    """Fichier tronqué ou corrompu : on refuse, on ne laisse pas passer."""
    for mauvais in ("", "n'importe quoi", "pbkdf2_sha256$abc$def", "a$b$c$d"):
        assert adminauth.verifier("secret", mauvais) is False
