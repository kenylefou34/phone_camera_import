import datetime
from phototheque import ingest
from mediasort import dates
from mediasort.catalog import Catalog


def test_sort_session_returns_bilan(tmp_path, monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    sess = tmp_path / "sess"; (sess / "Pictures").mkdir(parents=True)
    (sess / "Pictures" / "a.jpg").write_bytes(b"photo")
    lib = tmp_path / "lib"; lib.mkdir()
    cat = Catalog(":memory:")
    bilan = ingest.sort_session(sess, lib, cat)
    assert bilan["sorted"] == 1 and bilan["photos"] == 1
    assert (lib / "Photos" / "2023" / "05 MAI" / "a.jpg").exists()
    cat.close()
