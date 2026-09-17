from phototheque import pairing


def test_pairing_payload():
    p = pairing.pairing_payload("http://nuc.local:8787", "secret123")
    assert p == {"url": "http://nuc.local:8787", "token": "secret123", "cert_sha256": None}


def test_qr_svg_is_svg():
    svg = pairing.qr_svg("bonjour")
    assert "<svg" in svg and "</svg>" in svg


def test_qr_svg_renders_inline_in_html():
    """Le QR doit s'afficher tel quel dans une page HTML.

    Régression : la fabrique par défaut produit des balises `<svg:rect>`, avec
    un préfixe de namespace. C'est valide dans un fichier .svg autonome, mais
    l'analyseur HTML ne gère pas les préfixes : il fabrique des éléments
    inconnus qui n'affichent rien, et le QR reste blanc.
    """
    svg = pairing.qr_svg("bonjour")
    assert "svg:" not in svg, "préfixe de namespace : invisible dans une page HTML"


def test_qr_svg_is_scalable_and_sized_for_screen():
    """Un viewBox et des dimensions en pixels : lisible à l'écran, pas en mm."""
    svg = pairing.qr_svg("bonjour", taille=320)
    assert "viewBox" in svg
    assert 'width="320"' in svg and 'height="320"' in svg
    assert "mm" not in svg


def test_qr_svg_par_defaut_assez_grand_pour_un_telephone():
    """360 px : marge de lisibilité suffisante une fois l'empreinte ajoutée.

    Avec l'empreinte du certificat, la charge passe d'environ 98 à 182
    caractères et le QR d'environ 49 à 65 modules de côté. À 280 px le
    décodage échouait déjà sous 250 px de large ; 360 px redonne de la marge
    pour un scan au téléphone, de biais ou sous un éclairage médiocre.
    """
    svg = pairing.qr_svg("x" * 182)
    assert 'width="360"' in svg and 'height="360"' in svg
