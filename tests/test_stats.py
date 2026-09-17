from pathlib import Path
from phototheque import stats
from mediasort.catalog import Catalog


def test_disk_stats(tmp_path):
    d = stats.disk_stats(tmp_path)
    assert d["total"] > 0 and d["libre"] >= 0
    assert 0 <= d["pourcentage_utilise"] <= 100


def test_media_stats(tmp_path):
    db = tmp_path / "cat.db"
    cat = Catalog(str(db))
    cat.add_media("h1", 10, "/lib/Photos/2023/a.jpg", "2023-05-26", "metadata")
    cat.add_media("h2", 20, "/lib/Videos/2023/b.mp4", "2023-05-26", "metadata")
    cat.close()
    m = stats.media_stats(db)
    assert m["photos"] == 1 and m["videos"] == 1


def test_disk_level_thresholds():
    """Le niveau d'alerte du disque, calculé à part pour être testable.

    Un ratio contre une limite se lit sur une jauge, pas sur un camembert à
    deux parts : la couleur seule ne doit pas porter l'information, d'où ce
    niveau qui sera aussi écrit en toutes lettres.
    """
    assert stats.disk_level(10) == "ok"
    assert stats.disk_level(79) == "ok"
    assert stats.disk_level(80) == "warning"
    assert stats.disk_level(89) == "warning"
    assert stats.disk_level(90) == "critical"
    assert stats.disk_level(100) == "critical"
