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


def test_lire_metadonnees_ecarte_un_chemin_a_saut_de_ligne():
    # « exiftool -@ - » lit UN argument par ligne : un nom de fichier portant
    # un saut de ligne y glisserait une option exiftool de son choix.
    entrees = []
    def ex(cmd, input=None, **kw):
        entrees.append(input)
        return subprocess.CompletedProcess(cmd, 0, stdout=b"[]", stderr=b"")
    f.lire_metadonnees(["/b/ok.jpg", "/b/x.jpg\n-o\n/tmp/y", "/b/z\r.jpg"], executer=ex)
    assert entrees[0].decode().split("\n") == ["/b/ok.jpg"]


def test_lire_metadonnees_sans_chemin_valide_n_appelle_pas_exiftool():
    ex = Enregistreur({"exiftool": b"[]"})
    assert f.lire_metadonnees(["/b/x.jpg\n-o"], executer=ex) == {}
    assert ex.commandes == []


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


class ExecuteurSs1Invalide:
    """Simule un ffmpeg qui « réussit » (code 0, fichier non vide) sur
    `-ss 1` sans rien produire d'exploitable, puis rend un vrai WebP sur
    `-ss 0` — le cas rencontré sur une vidéo de moins d'une seconde avec
    ffmpeg 4.4.2 (voir la docstring de `_en_tete_webp_valide`)."""
    def __init__(self):
        self.commandes = []

    def __call__(self, cmd, **kw):
        self.commandes.append(cmd)
        outil = Path(cmd[0]).name
        if outil == "ffmpeg":
            if cmd[cmd.index("-ss") + 1] == "1":
                Path(cmd[-1]).write_bytes(b"deuxoct.")     # 8 octets, pas un WebP
            else:
                Path(cmd[-1]).write_bytes(b"RIFF....WEBP")
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        if outil == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout=b"400,225\n", stderr=b"")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")


def test_video_ss1_invalide_bascule_sur_ss0(tmp_path):
    ex = ExecuteurSs1Invalide()
    cible = tmp_path / "v.webp"
    l, h, methode = f.fabriquer_vignette("/b/v.mp4", "video", {}, cible, executer=ex)
    assert (l, h, methode) == (400, 225, "video")
    appels_ffmpeg = [c for c in ex.commandes if Path(c[0]).name == "ffmpeg"]
    assert len(appels_ffmpeg) == 2, "deux essais : -ss 1 puis -ss 0"
    assert appels_ffmpeg[0][appels_ffmpeg[0].index("-ss") + 1] == "1"
    assert appels_ffmpeg[1][appels_ffmpeg[1].index("-ss") + 1] == "0"
    assert cible.exists()
    assert not cible.with_name(cible.name + ".partiel").exists(), \
        "aucun fichier partiel laissé derrière l'essai raté"


def test_video_deux_essais_invalides_leve_erreur(tmp_path):
    def ex(cmd, **kw):
        if Path(cmd[0]).name == "ffmpeg":
            Path(cmd[-1]).write_bytes(b"deuxoct.")         # invalide aux deux essais
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
    cible = tmp_path / "v.webp"
    with pytest.raises(f.ErreurVignette):
        f.fabriquer_vignette("/b/v.mp4", "video", {}, cible, executer=ex)
    assert not cible.exists()
    assert not cible.with_name(cible.name + ".partiel").exists()


def test_fabriquer_moyenne_applique_orientation_et_borne_a_1280(tmp_path):
    ex = Enregistreur()
    cible = tmp_path / "m.webp"
    f.fabriquer_moyenne("/b/a.jpg", 6, cible, executer=ex)
    ffmpeg = next(c for c in ex.commandes if c[0] == "ffmpeg")
    assert "-noautorotate" in ffmpeg
    vf = ffmpeg[ffmpeg.index("-vf") + 1]
    assert vf.startswith("transpose=1")
    assert "min(1280,iw)" in vf
    assert cible.exists()


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
    # Assertion sur les dimensions réelles (pas seulement la méthode) : sur
    # le code d'avant le correctif de l'en-tête WebP, ce test passait quand
    # même avec un résultat bidon (0, 0) — voir task-5-report.md.
    src = tmp_path / "courte.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=640x360:duration=0.5", "-pix_fmt", "yuv420p", str(src)],
                   check=True)
    assert f.fabriquer_vignette(str(src), "video", {}, tmp_path / "v.webp") == (400, 225, "video")


@AVEC_FFMPEG
def test_vrai_fichier_corrompu(tmp_path):
    src = tmp_path / "casse.jpg"
    src.write_bytes(b"pas une image")
    with pytest.raises(f.ErreurVignette):
        f.fabriquer_vignette(str(src), "photo", {}, tmp_path / "v.webp")


@AVEC_FFMPEG
def test_vraie_moyenne_reduite_a_1280(tmp_path):
    src = tmp_path / "grande.jpg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=3000x2000", "-frames:v", "1", str(src)], check=True)
    cible = tmp_path / "m.webp"
    f.fabriquer_moyenne(str(src), None, cible)
    largeur, _ = f._dimensions(cible, subprocess.run)
    assert largeur == 1280
