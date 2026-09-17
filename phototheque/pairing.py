"""Charge utile d'appairage + génération du QR code (SVG, sans Pillow)."""

import re

import qrcode
import qrcode.image.svg


def pairing_payload(url: str, token: str, cert_sha256=None) -> dict:
    """Données encodées dans le QR d'appairage. Trois champs, et pas un de plus :

    - `url` : où joindre le serveur (schéma `https`). Sert à l'amorçage et de
      secours ; l'identité du serveur, elle, c'est son certificat.
    - `token` : le secret que l'application enverra en
      « Authorization: Bearer <token> ». Montré une seule fois.
    - `cert_sha256` : SHA-256 du certificat au format DER, en hexadécimal
      minuscule — l'empreinte que l'application ÉPINGLE pour reconnaître le
      serveur. Vaut `null` quand le service tourne sans certificat (lancement
      à la main en HTTP, ou certificat abîmé) : le serveur n'est alors pas
      épinglable.
    """
    return {"url": url, "token": token, "cert_sha256": cert_sha256}


def qr_svg(data: str, taille: int = 360) -> str:
    """Rend un QR code en SVG, prêt à être inséré dans une page HTML.

    On utilise SvgPathImage et non la fabrique par défaut, pour deux raisons :

    1. La fabrique par défaut produit des balises `<svg:rect>`, avec un préfixe
       de namespace. C'est correct dans un fichier .svg autonome, mais inséré
       dans du HTML l'analyseur ne gère pas les préfixes : il crée des éléments
       inconnus qui n'affichent rien et le QR reste blanc.
    2. Elle est six fois plus légère (un seul `<path>` au lieu d'un millier de
       rectangles) et fournit un `viewBox`, donc redimensionnable.

    Les dimensions d'origine sont en millimètres (unités d'impression) : on les
    remplace par des pixels pour un affichage prévisible à l'écran.
    """
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage)
    svg = img.to_string(encoding="unicode")
    svg = re.sub(r'width="[\d.]+mm"', f'width="{taille}"', svg, count=1)
    svg = re.sub(r'height="[\d.]+mm"', f'height="{taille}"', svg, count=1)
    return svg
