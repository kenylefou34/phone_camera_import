import hashlib
from mediasort import hashing


def test_file_hash_matches_hashlib(tmp_path):
    f = tmp_path / "a.bin"
    contenu = b"bonjour" * 1000
    f.write_bytes(contenu)
    assert hashing.file_hash(f) == hashlib.sha256(contenu).hexdigest()


def test_file_hash_differs_for_different_content(tmp_path):
    a = tmp_path / "a.bin"; a.write_bytes(b"aaa")
    b = tmp_path / "b.bin"; b.write_bytes(b"bbb")
    assert hashing.file_hash(a) != hashing.file_hash(b)


def test_quick_signature_stable_and_differs(tmp_path):
    from mediasort.hashing import quick_signature
    a = tmp_path / "a.bin"; a.write_bytes(b"x" * 200000)
    b = tmp_path / "b.bin"; b.write_bytes(b"x" * 200000)
    c = tmp_path / "c.bin"; c.write_bytes(b"y" * 200000)
    assert quick_signature(a) == quick_signature(b)  # même contenu -> même signature
    assert quick_signature(a) != quick_signature(c)  # contenu différent -> différente


def test_quick_signature_small_file(tmp_path):
    from mediasort.hashing import quick_signature
    p = tmp_path / "petit.bin"; p.write_bytes(b"court")
    assert isinstance(quick_signature(p), str) and len(quick_signature(p)) == 64


def test_copy_and_hash_copies_content_and_returns_its_hash(tmp_path):
    """La copie est fidèle et l'empreinte renvoyée est celle du contenu."""
    src = tmp_path / "video.mp4"
    contenu = b"bloc-de-video" * 200000  # plusieurs blocs de lecture
    src.write_bytes(contenu)
    dest = tmp_path / "copie.mp4"

    empreinte = hashing.copy_and_hash(src, dest)

    assert dest.read_bytes() == contenu
    assert empreinte == hashing.file_hash(src)


def test_copy_and_hash_preserves_mtime(tmp_path):
    """La date de modification est conservée (dernier recours de datation)."""
    import os
    src = tmp_path / "a.jpg"; src.write_bytes(b"photo")
    os.utime(src, (1000000000, 1000000000))  # 2001-09-09
    dest = tmp_path / "b.jpg"

    hashing.copy_and_hash(src, dest)

    assert dest.stat().st_mtime == src.stat().st_mtime


def test_copy_and_hash_reads_the_source_only_once(tmp_path, monkeypatch):
    """La source n'est ouverte en lecture qu'une seule fois."""
    import builtins
    src = tmp_path / "a.jpg"; src.write_bytes(b"photo")
    dest = tmp_path / "b.jpg"
    lectures = []
    vrai_open = builtins.open

    def espion(fichier, mode="r", *a, **kw):
        if "r" in mode and str(fichier) == str(src):
            lectures.append(str(fichier))
        return vrai_open(fichier, mode, *a, **kw)

    monkeypatch.setattr(builtins, "open", espion)
    hashing.copy_and_hash(src, dest)

    assert len(lectures) == 1
