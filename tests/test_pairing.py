from phototheque import pairing


def test_pairing_payload():
    p = pairing.pairing_payload("http://nuc.local:8787", "secret123")
    assert p == {"url": "http://nuc.local:8787", "token": "secret123", "cert_sha256": None}


def test_qr_svg_is_svg():
    svg = pairing.qr_svg("bonjour")
    assert "<svg" in svg and "</svg>" in svg
