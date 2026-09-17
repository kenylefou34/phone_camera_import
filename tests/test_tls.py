"""Tests de l'empreinte de certificat (épinglage côté application)."""

import hashlib
import ssl
import subprocess

import pytest

from phototheque import tls


def _certificat(tmp_path):
    """Fabrique un vrai certificat auto-signé pour le test."""
    cert = tmp_path / "cert.pem"
    cle = tmp_path / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-subj", "/CN=essai.local", "-keyout", str(cle), "-out", str(cert)],
        check=True, capture_output=True,
    )
    return cert


def test_empreinte_est_le_sha256_du_der(tmp_path):
    """L'empreinte est celle qu'un client TLS calculera de son côté."""
    cert = _certificat(tmp_path)
    attendu = hashlib.sha256(
        ssl.PEM_cert_to_DER_cert(cert.read_text())
    ).hexdigest()

    assert tls.empreinte_certificat(cert) == attendu


def test_empreinte_est_en_hexa_minuscule_de_64_caracteres(tmp_path):
    """Format attendu par l'application : 64 caractères hexadécimaux."""
    empreinte = tls.empreinte_certificat(_certificat(tmp_path))
    assert len(empreinte) == 64
    assert empreinte == empreinte.lower()
    assert all(c in "0123456789abcdef" for c in empreinte)


def test_deux_certificats_ont_des_empreintes_differentes(tmp_path):
    """Deux machines distinctes ont deux identités distinctes."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a = _certificat(tmp_path / "a")
    b = _certificat(tmp_path / "b")
    assert tls.empreinte_certificat(a) != tls.empreinte_certificat(b)


def test_certificat_absent_leve_une_erreur_claire(tmp_path):
    with pytest.raises(FileNotFoundError):
        tls.empreinte_certificat(tmp_path / "absent.pem")
