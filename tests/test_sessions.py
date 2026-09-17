import pytest
from phototheque import sessions


def test_save_upload_writes_under_session(tmp_path):
    s = sessions.new_session()
    p = sessions.save_upload(tmp_path, s, "Pictures/WhatsApp/a.jpg", b"data")
    assert p.read_bytes() == b"data"
    assert (tmp_path / s / "Pictures" / "WhatsApp" / "a.jpg") == p


def test_save_upload_rejects_traversal(tmp_path):
    s = sessions.new_session()
    with pytest.raises(ValueError):
        sessions.save_upload(tmp_path, s, "../../etc/passwd", b"x")
    with pytest.raises(ValueError):
        sessions.save_upload(tmp_path, s, "/abs/chemin.jpg", b"x")


def test_cleanup_removes_session(tmp_path):
    s = sessions.new_session()
    sessions.save_upload(tmp_path, s, "a.jpg", b"x")
    sessions.cleanup(tmp_path, s)
    assert not (tmp_path / s).exists()


def test_identifiant_valide_reconnait_ce_que_produit_new_session():
    """La forme attendue : 32 caractères hexadécimaux, rien d'autre."""
    assert sessions.identifiant_valide(sessions.new_session())
    for mauvais in ("", "inexistante", "../..", "/etc", "a" * 31, "A" * 32,
                    sessions.new_session() + "x"):
        assert not sessions.identifiant_valide(mauvais), mauvais


def test_un_identifiant_de_session_hors_norme_ne_sort_pas_du_dossier(tmp_path):
    """L'identifiant de session lui-même doit être contrôlé, pas seulement le
    chemin du fichier : « .. » comme session ferait écrire — puis effacer par
    le nettoyage de fin de synchro — un dossier voisin du dépôt des envois."""
    base = tmp_path / "incoming"
    voisin = tmp_path / "a_ne_pas_toucher"
    voisin.mkdir(parents=True)
    (voisin / "precieux.txt").write_text("à garder")

    with pytest.raises(ValueError):
        sessions.save_upload(base, "../a_ne_pas_toucher", "a.jpg", b"x")
    with pytest.raises(ValueError):
        sessions.cleanup(base, "../a_ne_pas_toucher")

    assert (voisin / "precieux.txt").exists()
