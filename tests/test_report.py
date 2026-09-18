import datetime, pathlib
from mediasort import sorter, dates
from mediasort.catalog import Catalog


def test_report_detailed_counters(tmp_path, monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "WhatsApp").mkdir()
    (src / "photo.jpg").write_bytes(b"une photo")
    (src / "film.mp4").write_bytes(b"une video")
    (src / "WhatsApp" / "wa.jpg").write_bytes(b"wa photo")
    cat = Catalog(":memory:")
    r = sorter.sort_folder(src, lib, cat, dry_run=False)
    d = r.to_dict()
    assert d["sorted"] == 3
    assert d["photos"] == 2 and d["videos"] == 1
    assert d["whatsapp"] == 1
    assert d["par_source_date"]["metadata"] == 3
    assert d["par_annee_mois"]["2023/05 MAI"] == 3
    assert d["octets_ranges"] > 0
    cat.close()
