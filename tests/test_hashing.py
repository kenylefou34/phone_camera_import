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
