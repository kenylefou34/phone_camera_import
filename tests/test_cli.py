import datetime
from mediasort import cli, dates
from mediasort.catalog import Catalog


def test_cli_dry_run_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    db = tmp_path / "cat.db"

    code = cli.main(["--source", str(src), "--library", str(lib),
                     "--catalog", str(db), "--dry-run"])

    assert code == 0
    sortie = capsys.readouterr().out
    assert "rangé" in sortie.lower() or "range" in sortie.lower()
    assert (src / "a.jpg").exists()  # dry-run


def test_cli_seed_from_scopes_catalog(tmp_path, monkeypatch):
    from mediasort.catalog import Catalog
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    lib = tmp_path / "lib"
    (lib / "Photos" / "2023").mkdir(parents=True)
    (lib / "WhatsApp").mkdir()
    (lib / "Photos" / "2023" / "cam.jpg").write_bytes(b"camera")
    (lib / "WhatsApp" / "wa.jpg").write_bytes(b"whatsapp")
    src = tmp_path / "src"; src.mkdir()
    db = tmp_path / "cat.db"

    cli.main(["--source", str(src), "--library", str(lib), "--catalog", str(db),
              "--seed", "--seed-from", str(lib / "WhatsApp"), "--dry-run"])

    cat = Catalog(str(db))
    assert cat.count() == 1  # seule wa.jpg indexée, pas cam.jpg
    cat.close()
