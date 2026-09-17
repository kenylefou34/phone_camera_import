"""Charge utile d'appairage + génération du QR code (SVG, sans Pillow)."""

import qrcode
import qrcode.image.svg


def pairing_payload(url: str, token: str, cert_sha256=None) -> dict:
    """Données encodées dans le QR : où joindre le NUC + secret (+ empreinte certif future)."""
    return {"url": url, "token": token, "cert_sha256": cert_sha256}


def qr_svg(data: str) -> str:
    """Rend un QR code au format SVG (chaîne)."""
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgImage)
    return img.to_string(encoding="unicode")
