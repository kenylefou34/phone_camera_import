from mediasort.catalog import Catalog


def test_add_and_has_hash():
    cat = Catalog(":memory:")
    assert cat.has_hash("abc") is False
    cat.add_media("abc", 10, "/lib/x.jpg", "2023-05-26", "metadata")
    assert cat.has_hash("abc") is True
    assert cat.count() == 1
    cat.close()


def test_add_media_is_idempotent_on_hash():
    cat = Catalog(":memory:")
    cat.add_media("abc", 10, "/lib/x.jpg", "2023-05-26", "metadata")
    cat.add_media("abc", 10, "/lib/copie.jpg", "2023-05-26", "metadata")
    assert cat.count() == 1
    cat.close()


def test_last_sync_roundtrip():
    cat = Catalog(":memory:")
    assert cat.get_last_sync("Camera") is None
    cat.set_last_sync("Camera", 1234.5)
    assert cat.get_last_sync("Camera") == 1234.5
    cat.close()


def test_seed_from_library_indexes_media(tmp_path):
    (tmp_path / "Photos" / "2023").mkdir(parents=True)
    (tmp_path / "Photos" / "2023" / "a.jpg").write_bytes(b"photo-a")
    (tmp_path / "notes.txt").write_bytes(b"pas un media")
    cat = Catalog(":memory:")
    n = cat.seed_from_library(tmp_path)
    assert n == 1  # seule a.jpg est indexée
    assert cat.count() == 1
    cat.close()
