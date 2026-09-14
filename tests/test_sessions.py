import pytest
from mediaserve import sessions


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
