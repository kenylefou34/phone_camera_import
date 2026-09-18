import pathlib
from mediasort import noise


def test_is_noise():
    assert noise.is_noise(pathlib.Path("/x/vocal.opus")) is True
    assert noise.is_noise(pathlib.Path("/x/msgstore.db.crypt14")) is True
    assert noise.is_noise(pathlib.Path("/x/.nomedia")) is True
    assert noise.is_noise(pathlib.Path("/x/._IMG_0001.MP4")) is True  # AppleDouble
    assert noise.is_noise(pathlib.Path("/x/IMG_0001.jpg")) is False


def test_clean_noise_dry_run_removes_nothing(tmp_path):
    bruit = tmp_path / "vocal.opus"; bruit.write_bytes(b"x")
    listes = noise.clean_noise(tmp_path, dry_run=True)
    assert bruit in listes
    assert bruit.exists()  # dry-run : rien supprimé


def test_clean_noise_removes_noise(tmp_path):
    bruit = tmp_path / "vocal.opus"; bruit.write_bytes(b"x")
    garde = tmp_path / "photo.jpg"; garde.write_bytes(b"y")
    listes = noise.clean_noise(tmp_path, dry_run=False)
    assert not bruit.exists()
    assert garde.exists()
    assert bruit in listes
