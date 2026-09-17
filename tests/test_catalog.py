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


def test_seed_from_library_excludes_source(tmp_path):
    (tmp_path / "Photos" / "2023").mkdir(parents=True)
    (tmp_path / "Photos" / "2023" / "a.jpg").write_bytes(b"photo-a")
    (tmp_path / "unsorted").mkdir()
    (tmp_path / "unsorted" / "b.jpg").write_bytes(b"photo-b")
    cat = Catalog(":memory:")
    n = cat.seed_from_library(tmp_path, exclude=[tmp_path / "unsorted"])
    assert n == 1  # seule Photos/2023/a.jpg indexée, pas unsorted/b.jpg
    cat.close()


def test_add_media_stores_signature():
    """La signature rapide est enregistrée et retrouvée."""
    cat = Catalog(":memory:")
    assert cat.has_signature("sig-abc") is False
    cat.add_media("abc", 10, "/lib/x.jpg", "2023-05-26", "metadata", signature="sig-abc")
    assert cat.has_signature("sig-abc") is True
    cat.close()


def test_signatures_complete_false_when_a_row_lacks_signature():
    """Garde-fou : le pré-filtre n'est sûr que si TOUTES les lignes ont une signature."""
    cat = Catalog(":memory:")
    assert cat.signatures_complete() is True  # catalogue vide : rien ne manque
    cat.add_media("abc", 10, "/lib/x.jpg", None, "seed", signature="sig-abc")
    assert cat.signatures_complete() is True
    cat.add_media("def", 10, "/lib/y.jpg", None, "seed")  # sans signature (ancien import)
    assert cat.signatures_complete() is False
    cat.close()


def test_opens_old_catalog_without_signature_column(tmp_path):
    """Un catalogue d'avant la colonne 'signature' est migré sans perdre ses lignes."""
    import sqlite3
    db = tmp_path / "ancien.db"
    cx = sqlite3.connect(str(db))
    cx.execute(
        "CREATE TABLE medias ( empreinte TEXT PRIMARY KEY, taille INTEGER,"
        " chemin TEXT, date_prise TEXT, source_date TEXT,"
        " date_import TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    cx.execute("INSERT INTO medias (empreinte, taille, chemin) VALUES ('vieux', 1, '/lib/a.jpg')")
    cx.commit()
    cx.close()

    cat = Catalog(db)
    assert cat.count() == 1               # les lignes existantes sont conservées
    assert cat.has_hash("vieux") is True
    assert cat.signatures_complete() is False  # l'ancienne ligne n'a pas de signature
    cat.close()


def test_seed_from_library_fills_signature(tmp_path):
    """L'amorçage enregistre la signature : le pré-filtre devient utilisable."""
    (tmp_path / "Photos").mkdir()
    (tmp_path / "Photos" / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")
    cat.seed_from_library(tmp_path)
    assert cat.signatures_complete() is True
    from mediasort.hashing import quick_signature
    assert cat.has_signature(quick_signature(tmp_path / "Photos" / "a.jpg")) is True
    cat.close()


def test_backfill_signatures_fills_existing_rows(tmp_path):
    """Rattrapage : calcule les signatures manquantes à partir du chemin stocké."""
    from mediasort.hashing import quick_signature
    media = tmp_path / "a.jpg"
    media.write_bytes(b"photo-a")
    cat = Catalog(":memory:")
    cat.add_media("h-a", 7, str(media), None, "seed")  # ancienne ligne, sans signature
    assert cat.signatures_complete() is False

    n = cat.backfill_signatures()

    assert n == 1
    assert cat.signatures_complete() is True
    assert cat.has_signature(quick_signature(media)) is True
    cat.close()


def test_backfill_signatures_skips_unreadable_files(tmp_path):
    """Un fichier disparu ne bloque pas le rattrapage (sa ligne reste sans signature)."""
    cat = Catalog(":memory:")
    cat.add_media("h-disparu", 7, str(tmp_path / "absent.jpg"), None, "seed")
    n = cat.backfill_signatures()
    assert n == 0
    assert cat.signatures_complete() is False  # donc le pré-filtre reste désactivé
    cat.close()
