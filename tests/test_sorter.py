import datetime
import pathlib
from mediasort import sorter, dates
from mediasort.catalog import Catalog


def _force_date(monkeypatch, d):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: d)


def test_sort_places_photo_by_date(tmp_path, monkeypatch):
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.sorted == 1
    assert (lib / "Photos" / "2023" / "05 MAI" / "a.jpg").exists()
    assert not (src / "a.jpg").exists()  # source retirée après copie vérifiée
    cat.close()


def test_sort_dry_run_moves_nothing(tmp_path, monkeypatch):
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=True)

    assert report.sorted == 1  # compté comme "serait rangé"
    assert (src / "a.jpg").exists()  # rien déplacé
    assert not (lib / "Photos").exists()
    cat.close()


def test_sort_skips_duplicate(tmp_path, monkeypatch):
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    (src / "copie.jpg").write_bytes(b"photo-a")  # même contenu
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.sorted == 1
    assert report.duplicates == 1
    cat.close()


def test_sort_unknown_date_goes_to_triage(tmp_path, monkeypatch):
    _force_date(monkeypatch, None)
    monkeypatch.setattr(dates, "date_from_filesystem", lambda p: None)
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "mystere.jpg").write_bytes(b"x")
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.to_triage == 1
    assert (lib / "_A_TRIER" / "mystere.jpg").exists()
    cat.close()


def _compter_hash_complets(monkeypatch):
    """Espionne file_hash dans le trieur et renvoie la liste des fichiers hachés."""
    appels = []
    vrai_hash = sorter.file_hash

    def espion(path):
        appels.append(pathlib.Path(path).name)
        return vrai_hash(path)

    monkeypatch.setattr(sorter, "file_hash", espion)
    return appels


def test_sort_skips_full_hash_when_signature_unknown(tmp_path, monkeypatch):
    """Pré-filtre : signature inconnue => le fichier n'est pas haché en entier."""
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "grosse-video.mp4").write_bytes(b"video" * 1000)
    cat = Catalog(":memory:")  # vide => signatures complètes, pré-filtre actif
    appels = _compter_hash_complets(monkeypatch)

    report = sorter.sort_folder(src, lib, cat, dry_run=True)

    assert report.sorted == 1
    assert appels == []  # aucun hachage complet : la signature a suffi
    cat.close()


def test_sort_still_detects_duplicate_with_prefilter(tmp_path, monkeypatch):
    """Pré-filtre actif : un vrai doublon est toujours reconnu (hash complet fait)."""
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    (src / "copie.jpg").write_bytes(b"photo-a")  # même contenu
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.sorted == 1
    assert report.duplicates == 1
    assert cat.signatures_complete() is True  # la signature est enregistrée au rangement
    cat.close()


def test_sort_detects_duplicate_when_catalog_has_no_signatures(tmp_path, monkeypatch):
    """Garde-fou : sur un vieux catalogue sans signatures, le pré-filtre est désactivé.

    Sans ce garde-fou, le doublon passerait inaperçu et serait copié en double.
    """
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")
    # Ligne d'ancien format : empreinte connue, mais aucune signature.
    from mediasort.hashing import file_hash
    cat.add_media(file_hash(src / "a.jpg"), 7, "/lib/deja.jpg", None, "seed")
    assert cat.signatures_complete() is False

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.duplicates == 1
    assert report.sorted == 0
    cat.close()
