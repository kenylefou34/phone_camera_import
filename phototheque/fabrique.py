"""Fabrique des vignettes : exiftool et ffmpeg, rien d'autre (spec §3).

Le coût, c'est d'OUVRIR le fichier sur un disque NTFS à ~7 Mo/s, pas de le
traiter. D'où trois chemins, du moins cher au plus cher :

- photo avec vignette EXIF (73 % des JPEG, mesuré) : `exiftool` n'en lit que
  l'en-tête. Cette vignette fait ~160 px ; elle est gardée à sa taille, jamais
  agrandie (elle deviendrait floue) ;
- photo sans vignette EXIF : `ffmpeg` décode le fichier entier ;
- vidéo : `ffmpeg -ss 1 -i …` saute à la première seconde SANS décoder ce qui
  précède, et ne lit donc que le début du fichier.

L'orientation EXIF (photo prise en portrait) est appliquée par nous, à partir
de la balise lue par exiftool, et `-noautorotate` empêche ffmpeg de la
réappliquer une seconde fois. Les vidéos, elles, gardent la rotation
automatique de ffmpeg (métadonnée de conteneur, pas EXIF).
"""

import json
import subprocess
from pathlib import Path

TAILLE_VIGNETTE = 400
TAILLE_MOYENNE = 1280

# Balises lues en un seul appel par lot. `-n` rend Orientation et
# ThumbnailLength numériques ; les dates restent du texte « AAAA:MM:JJ hh:mm:ss ».
_BALISES = ["DateTimeOriginal", "CreateDate", "CreationDate", "MediaCreateDate",
            "Orientation", "ThumbnailLength"]

# Orientation EXIF → filtre ffmpeg (1 = rien à faire).
_ROTATIONS = {2: "hflip", 3: "hflip,vflip", 4: "vflip", 5: "transpose=0",
              6: "transpose=1", 7: "transpose=3", 8: "transpose=2"}


class ErreurVignette(Exception):
    """La vignette n'a pas pu être faite ; le message dit pourquoi."""


def filtre(orientation: int | None, taille: int) -> str:
    """Chaîne `-vf` : redresser, puis réduire à `taille` sans jamais agrandir."""
    etapes = []
    if orientation in _ROTATIONS:
        etapes.append(_ROTATIONS[orientation])
    etapes.append(f"scale='min({taille},iw)':'min({taille},ih)'"
                  ":force_original_aspect_ratio=decrease")
    return ",".join(etapes)


def lire_metadonnees(chemins: list[str], executer=subprocess.run) -> dict[str, dict]:
    """Balises utiles de tout un lot, en UN appel exiftool (liste sur l'entrée
    standard : pas de limite de longueur de ligne de commande)."""
    if not chemins:
        return {}
    cmd = ["exiftool", "-json", "-n", "-api", "QuickTimeUTC=1",
           *[f"-{b}" for b in _BALISES], "-@", "-"]
    r = executer(cmd, input="\n".join(chemins).encode(), capture_output=True, timeout=600)
    try:
        lignes = json.loads(r.stdout or b"[]")
    except json.JSONDecodeError:
        return {}
    return {d.get("SourceFile"): d for d in lignes if isinstance(d, dict)}


def _dimensions(fichier: Path, executer) -> tuple[int, int]:
    r = executer(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "stream=width,height", "-of", "csv=p=0", str(fichier)],
                 capture_output=True, timeout=60)
    try:
        largeur, hauteur = (int(x) for x in r.stdout.decode().strip().split(",")[:2])
    except ValueError as e:
        raise ErreurVignette(f"dimensions illisibles : {r.stdout!r}") from e
    return largeur, hauteur


def _en_tete_webp_valide(fichier: Path) -> bool:
    """Un WebP a toujours un conteneur RIFF/WEBP d'au moins 12 octets. Ce
    contrôle attrape un cas vu avec un vrai ffmpeg (4.4.2) : chercher `-ss`
    au-delà de la fin d'une vidéo très courte rend un code de retour 0 et un
    fichier non vide (8 octets de bruit), mais qui n'est pas une image —
    juste vérifier que la taille est non nulle laisse passer ce faux succès,
    et prive la vidéo de son repli `-ss 0`."""
    try:
        entete = fichier.read_bytes()[:12]
    except OSError:
        return False
    return len(entete) == 12 and entete[:4] == b"RIFF" and entete[8:12] == b"WEBP"


def _ffmpeg(avant_entree: list[str], entree: str, vf: str, cible: Path,
            executer, donnees: bytes | None = None) -> bool:
    """Une image WebP dans `cible`, écrite à côté puis renommée (jamais de
    fichier à moitié écrit). Faux si ffmpeg n'a rien produit d'exploitable."""
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = cible.with_name(cible.name + ".partiel")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *avant_entree,
           "-i", entree, "-frames:v", "1", "-vf", vf,
           "-c:v", "libwebp", "-quality", "75", "-f", "webp", str(partiel)]
    r = executer(cmd, input=donnees, capture_output=True, timeout=300)
    if r.returncode != 0 or not partiel.exists() or not _en_tete_webp_valide(partiel):
        partiel.unlink(missing_ok=True)
        _ffmpeg.derniere_erreur = (r.stderr or b"").decode(errors="replace")[-300:]
        return False
    partiel.replace(cible)
    return True


_ffmpeg.derniere_erreur = ""


def fabriquer_vignette(chemin: str, type_: str, meta: dict, cible: Path,
                       executer=subprocess.run) -> tuple[int, int, str]:
    """Écrit la vignette de `chemin` dans `cible` ; renvoie (largeur, hauteur, méthode)."""
    orientation = meta.get("Orientation")
    if type_ == "video":
        vf = filtre(None, TAILLE_VIGNETTE)
        if not (_ffmpeg(["-ss", "1"], chemin, vf, cible, executer)
                or _ffmpeg(["-ss", "0"], chemin, vf, cible, executer)):
            raise ErreurVignette(f"ffmpeg (vidéo) : {_ffmpeg.derniere_erreur}")
        return (*_dimensions(cible, executer), "video")

    vf = filtre(orientation, TAILLE_VIGNETTE)
    if meta.get("ThumbnailLength"):
        r = executer(["exiftool", "-b", "-ThumbnailImage", chemin],
                     capture_output=True, timeout=60)
        if r.stdout and _ffmpeg(["-noautorotate", "-f", "jpeg_pipe"], "-", vf, cible,
                                executer, donnees=r.stdout):
            return (*_dimensions(cible, executer), "exif")
    if not _ffmpeg(["-noautorotate"], chemin, vf, cible, executer):
        raise ErreurVignette(f"ffmpeg (photo) : {_ffmpeg.derniere_erreur}")
    return (*_dimensions(cible, executer), "photo")


def fabriquer_moyenne(chemin: str, orientation: int | None, cible: Path,
                      executer=subprocess.run) -> None:
    """Taille intermédiaire (1280 px) d'une photo, pour l'affichage en grand."""
    if not _ffmpeg(["-noautorotate"], chemin, filtre(orientation, TAILLE_MOYENNE),
                   cible, executer):
        raise ErreurVignette(f"ffmpeg (moyenne) : {_ffmpeg.derniere_erreur}")
