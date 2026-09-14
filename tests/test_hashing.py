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
