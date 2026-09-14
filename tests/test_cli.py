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
