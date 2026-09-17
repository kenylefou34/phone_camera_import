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


def test_pie_svg(tmp_path):
    svg = stats.pie_svg(used=700, free=300)
    assert "<svg" in svg and "</svg>" in svg
