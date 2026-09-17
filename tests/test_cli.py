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


def test_cli_backfill_signatures_without_source(tmp_path, capsys):
    """--backfill-signatures complète un ancien catalogue, sans exiger --source."""
    media = tmp_path / "a.jpg"
    media.write_bytes(b"photo-a")
    db = tmp_path / "cat.db"
    cat = Catalog(str(db))
    cat.add_media("h-a", 7, str(media), None, "seed")  # ligne d'ancien format
    assert cat.signatures_complete() is False
    cat.close()

    code = cli.main(["--catalog", str(db), "--backfill-signatures"])

    assert code == 0
    assert "1" in capsys.readouterr().out
    cat = Catalog(str(db))
    assert cat.signatures_complete() is True
    cat.close()


def test_cli_requires_source_and_library_for_sorting(tmp_path, capsys):
    """Sans --backfill-signatures, --source et --library restent obligatoires."""
    import pytest
    with pytest.raises(SystemExit) as sortie:
        cli.main(["--catalog", str(tmp_path / "cat.db")])
    assert sortie.value.code == 2
    assert "source" in capsys.readouterr().err.lower()
