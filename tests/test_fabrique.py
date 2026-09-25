"""Tests de la fabrique de vignettes (commandes, puis vrais outils si présents)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from phototheque import fabrique as f

AVEC_FFMPEG = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None
    or b"libwebp" not in subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                                         capture_output=True).stdout,
    reason="ffmpeg avec libwebp absent")


class Enregistreur:
    """Remplace subprocess.run : note les commandes, rend une réponse choisie."""
    def __init__(self, reponses=None):
        self.commandes = []
        self.reponses = reponses or {}

    def __call__(self, cmd, **kw):
        self.commandes.append(cmd)
        outil = Path(cmd[0]).name
        if outil == "ffmpeg":
            Path(cmd[-1]).write_bytes(b"RIFF....WEBP")      # le fichier de sortie
        sortie = self.reponses.get(outil, b"")
        return subprocess.CompletedProcess(cmd, 0, stdout=sortie, stderr=b"")


@pytest.mark.parametrize("orientation,attendu", [
    (None, ""), (1, ""), (3, "hflip,vflip"), (6, "transpose=1"), (8, "transpose=2")])
def test_filtre_applique_l_orientation_puis_reduit_sans_agrandir(orientation, attendu):
    vf = f.filtre(orientation, 400)
    assert vf.endswith("scale='min(400,iw)':'min(400,ih)':force_original_aspect_ratio=decrease")
    assert vf.startswith(attendu)


def test_lire_metadonnees_par_lot_et_indexe_par_chemin():
    rep = json.dumps([{"SourceFile": "/b/a.jpg", "DateTimeOriginal": "2019:05:04 10:00:00",
                       "Orientation": 6, "ThumbnailLength": 14000}]).encode()
    ex = Enregistreur({"exiftool": rep})
    meta = f.lire_metadonnees(["/b/a.jpg"], executer=ex)
    assert meta["/b/a.jpg"]["Orientation"] == 6
    cmd = ex.commandes[0]
    assert cmd[0] == "exiftool" and "-json" in cmd and "-n" in cmd


def test_photo_avec_vignette_exif_ne_lit_que_l_en_tete(tmp_path):
    ex = Enregistreur({"exiftool": b"\xff\xd8jpeg", "ffprobe": b"160,120\n"})
    l, h, methode = f.fabriquer_vignette("/b/a.jpg", "photo",
                                         {"ThumbnailLength": 14000, "Orientation": 6},
                                         tmp_path / "v.webp", executer=ex)
    assert (l, h, methode) == (160, 120, "exif")
    assert ex.commandes[0][:3] == ["exiftool", "-b", "-ThumbnailImage"]
    ffmpeg = next(c for c in ex.commandes if c[0] == "ffmpeg")
    assert "-noautorotate" in ffmpeg, "la rotation est la nôtre, pas celle de ffmpeg"
    assert "transpose=1" in ffmpeg[ffmpeg.index("-vf") + 1]
    assert (tmp_path / "v.webp").exists()


def test_photo_sans_vignette_exif_passe_par_ffmpeg(tmp_path):
    ex = Enregistreur({"ffprobe": b"400,300\n"})
    *_, methode = f.fabriquer_vignette("/b/a.jpg", "photo", {}, tmp_path / "v.webp", executer=ex)
    assert methode == "photo"
    assert not any(c[0] == "exiftool" for c in ex.commandes)


def test_video_ne_lit_que_le_debut(tmp_path):
    ex = Enregistreur({"ffprobe": b"400,225\n"})
    *_, methode = f.fabriquer_vignette("/b/v.mp4", "video", {}, tmp_path / "v.webp", executer=ex)
    ffmpeg = next(c for c in ex.commandes if c[0] == "ffmpeg")
    assert methode == "video"
    assert ffmpeg.index("-ss") < ffmpeg.index("-i"), "-ss AVANT -i : saut sans décoder"


def test_une_sortie_ffmpeg_vide_est_une_erreur(tmp_path):
    def ex(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Invalid data found")
    with pytest.raises(f.ErreurVignette, match="Invalid data"):
        f.fabriquer_vignette("/b/a.jpg", "photo", {}, tmp_path / "v.webp", executer=ex)
    assert not (tmp_path / "v.webp").exists(), "jamais de vignette à moitié écrite"


@AVEC_FFMPEG
def test_vraie_photo_reduite_a_400(tmp_path):
    src = tmp_path / "grande.jpg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=800x600", "-frames:v", "1", str(src)], check=True)
    assert f.fabriquer_vignette(str(src), "photo", {}, tmp_path / "v.webp")[:2] == (400, 300)


@AVEC_FFMPEG
def test_vraie_petite_photo_jamais_agrandie(tmp_path):
    src = tmp_path / "petite.jpg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=100x80", "-frames:v", "1", str(src)], check=True)
    assert f.fabriquer_vignette(str(src), "photo", {}, tmp_path / "v.webp")[:2] == (100, 80)


@AVEC_FFMPEG
def test_vraie_video_courte(tmp_path):
    # Moins d'une seconde : le saut à 1 s ne donne rien, on retente à 0.
    src = tmp_path / "courte.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=640x360:duration=0.5", "-pix_fmt", "yuv420p", str(src)],
                   check=True)
    assert f.fabriquer_vignette(str(src), "video", {}, tmp_path / "v.webp")[2] == "video"


@AVEC_FFMPEG
def test_vrai_fichier_corrompu(tmp_path):
    src = tmp_path / "casse.jpg"
    src.write_bytes(b"pas une image")
    with pytest.raises(f.ErreurVignette):
        f.fabriquer_vignette(str(src), "photo", {}, tmp_path / "v.webp")
