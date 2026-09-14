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
