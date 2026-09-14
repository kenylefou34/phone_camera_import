import datetime
from mediasort import dates


def test_date_from_filename_patterns():
    d = datetime.date(2023, 5, 26)
    assert dates.date_from_filename("IMG_20230526_101500.jpg") == d
    assert dates.date_from_filename("VID-20230526-WA0009.mp4") == d
    assert dates.date_from_filename("PXL_20230526_101500123.jpg") == d
    assert dates.date_from_filename("Screenshot_2023-05-26-10-15.png") == d
    assert dates.date_from_filename("signal-2023-05-26-101500.jpg") == d


def test_date_from_filename_none_when_absent():
    assert dates.date_from_filename("photo_sans_date.jpg") is None


def test_date_from_filename_rejects_impossible_dates():
    # 2023-13-40 n'est pas une date valide -> None
    assert dates.date_from_filename("IMG_20231340.jpg") is None


def test_pick_metadata_date_priority():
    tags = {
        "DateTimeOriginal": "2023:05:26 10:15:00",
        "CreateDate": "2020:01:01 00:00:00",
    }
    assert dates._pick_metadata_date(tags) == datetime.date(2023, 5, 26)


def test_pick_metadata_date_fallback_createdate():
    tags = {"CreateDate": "2019:07:04 12:00:00"}
    assert dates._pick_metadata_date(tags) == datetime.date(2019, 7, 4)


def test_pick_metadata_date_ignore_zero():
    # exiftool renvoie parfois des dates nulles -> ignorées
    tags = {"DateTimeOriginal": "0000:00:00 00:00:00"}
    assert dates._pick_metadata_date(tags) is None


def test_pick_metadata_date_empty():
    assert dates._pick_metadata_date({}) is None


import pathlib


def test_resolve_date_prefers_metadata(monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    r = dates.resolve_date(pathlib.Path("IMG_20200101.jpg"))
    assert r.date == datetime.date(2023, 5, 26)
    assert r.source == "metadata"


def test_resolve_date_falls_back_to_filename(monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: None)
    r = dates.resolve_date(pathlib.Path("IMG_20230526.jpg"))
    assert r.date == datetime.date(2023, 5, 26)
    assert r.source == "filename"


def test_resolve_date_falls_back_to_filesystem(tmp_path, monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: None)
    f = tmp_path / "sans_date.jpg"
    f.write_bytes(b"x")
    r = dates.resolve_date(f)
    assert r.source == "filesystem"
    assert isinstance(r.date, datetime.date)


def test_resolve_date_unknown_when_missing_file(monkeypatch):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: None)
    r = dates.resolve_date(pathlib.Path("/inexistant/sans_date.jpg"))
    assert r.source == "unknown"
    assert r.date is None


from types import SimpleNamespace


def test_exiftool_dates_for_parses_batch(monkeypatch):
    fake = __import__("json").dumps([
        {"SourceFile": "/x/a.jpg", "DateTimeOriginal": "2023:05:26 10:00:00"},
        {"SourceFile": "/x/b.mp4", "CreateDate": "2019:07:04 12:00:00"},
        {"SourceFile": "/x/c.png"},
    ])
    monkeypatch.setattr(dates.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=fake))
    res = dates.exiftool_dates_for([pathlib.Path("/x/a.jpg"), pathlib.Path("/x/b.mp4"), pathlib.Path("/x/c.png")])
    assert res["/x/a.jpg"] == datetime.date(2023, 5, 26)
    assert res["/x/b.mp4"] == datetime.date(2019, 7, 4)
    assert res["/x/c.png"] is None


def test_date_from_metadata_uses_cache(monkeypatch):
    appels = []
    monkeypatch.setattr(dates, "_exiftool_tags", lambda p: appels.append(p) or {})
    dates._META_CACHE = {"/x/a.jpg": datetime.date(2023, 5, 26)}
    try:
        assert dates.date_from_metadata(pathlib.Path("/x/a.jpg")) == datetime.date(2023, 5, 26)
        assert appels == []  # cache hit -> pas d'appel exiftool
        assert dates.date_from_metadata(pathlib.Path("/x/autre.jpg")) is None
        assert appels  # miss -> exiftool appelé
    finally:
        dates._META_CACHE = {}


def test_prefetch_metadata_populates_cache(monkeypatch):
    monkeypatch.setattr(dates, "exiftool_dates_for", lambda paths: {"/x/a.jpg": datetime.date(2023, 5, 26)})
    dates.prefetch_metadata([pathlib.Path("/x/a.jpg")])
    try:
        assert dates._META_CACHE == {"/x/a.jpg": datetime.date(2023, 5, 26)}
    finally:
        dates._META_CACHE = {}
