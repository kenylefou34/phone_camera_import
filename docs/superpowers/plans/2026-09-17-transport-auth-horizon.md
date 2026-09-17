# Transport chiffré, authentification admin, horizon de synchro — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** rendre le service joignable en HTTPS épinglable, protéger sa surface
d'administration par mot de passe, et donner à chaque appareil un horizon de
synchro par dossier — avant que l'app Android (#12) fige ce contrat.

**Architecture :** tout dans le service Python. `uvicorn` termine le TLS avec un
certificat auto-signé fabriqué par `install.sh` ; l'authentification admin est
une dépendance FastAPI comme l'actuelle `require_device` ; l'horizon déménage du
catalogue vers la base des appareils, clé par `(appareil, dossier)`.

**Tech Stack :** Python 3 (stdlib : `ssl`, `hashlib`, `hmac`, `sqlite3`),
FastAPI, uvicorn, openssl (CLI), bash, pytest.

**Spec :** `docs/superpowers/specs/2026-09-17-transport-auth-horizon-design.md`

## Global Constraints

- **Aucune dépendance Python nouvelle.** `cryptography` est absent du venv du NUC
  et doit le rester. Tout s'appuie sur `ssl`, `hashlib`, `hmac`, `sqlite3`.
- **Français** pour tout commentaire, docstring et message utilisateur
  (le mainteneur débute en Python). Noms de fonctions en anglais, comme
  l'existant (`pair`, `validate`, `list`, `revoke`).
- **TDD strict.** Aucun code de production sans test qui échoue d'abord.
- La suite entière doit rester verte à chaque commit : `python3 -m pytest -q`.
  Elle compte **115 tests** au démarrage de ce plan.
- **Migrations de schéma par `ALTER TABLE` idempotent**, sur le modèle de
  `DeviceStore._migrer_confirmation` : les bases existantes ne doivent jamais
  perdre de lignes.
- `deploy/install.sh` reste **idempotent** et ne régénère jamais un secret ou un
  certificat existant.
- **Aucune décision prise depuis un pipeline shell** sous `set -o pipefail`
  (cf. `tests/test_deploy.py::test_aucune_decision_prise_depuis_un_pipeline`).
- Chemin des secrets : `~/.config/phototheque/`, dossier `0700`, fichiers `0600`.

---

## Structure des fichiers

| Fichier | Responsabilité | Action |
|---|---|---|
| `phototheque/tls.py` | empreinte d'un certificat | **créer** |
| `phototheque/adminauth.py` | empreinte et vérification du mot de passe admin | **créer** |
| `phototheque/config.py` | chemins et URL publiée | modifier |
| `phototheque/devices.py` | horizons par (appareil, dossier) | modifier |
| `phototheque/app.py` | dépendance admin, routes `/pair` et `/sync/horizon` | modifier |
| `phototheque/web.py` | champ de date sur la page d'appairage | modifier |
| `mediasort/catalog.py` | retrait de la table `synchros` inutilisée | modifier |
| `deploy/phototheque.service` | arguments `--ssl-*` | modifier |
| `deploy/install.sh` | certificat, mot de passe, nom convivial | modifier |
| `tests/test_tls.py` | empreinte | **créer** |
| `tests/test_adminauth.py` | mot de passe | **créer** |
| `tests/test_app.py`, `test_devices.py`, `test_serve_config.py`, `test_catalog.py` | | modifier |
| `README.md`, `docs/DEPLOIEMENT.md` | adresses `https`, avertissement, migration | modifier |

---

## Task 1 : empreinte d'un certificat

**Files:**
- Create: `phototheque/tls.py`
- Test: `tests/test_tls.py`

**Interfaces:**
- Consumes: rien.
- Produces: `tls.empreinte_certificat(chemin: Path) -> str` — SHA-256 du
  certificat au format DER, en hexadécimal minuscule (64 caractères).
  Lève `FileNotFoundError` si le fichier n'existe pas.

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_tls.py
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
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_tls.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'phototheque.tls'`

- [ ] **Step 3 : écrire le module**

```python
# phototheque/tls.py
"""Empreinte du certificat servi, transmise à l'application pour épinglage."""

import hashlib
import ssl
from pathlib import Path


def empreinte_certificat(chemin: Path) -> str:
    """Renvoie le SHA-256 du certificat au format DER, en hexadécimal.

    C'est la forme standard de l'épinglage : l'application compare cette
    empreinte à celle du certificat que lui présente le serveur qu'elle joint.
    Un appareil qui usurperait le nom du NUC serait rejeté, même avec un
    certificat par ailleurs valide.

    On passe par le format DER et non par le texte PEM : le PEM est un
    encodage, deux fichiers PEM différents (retours à la ligne, commentaires)
    peuvent porter le même certificat.
    """
    pem = Path(chemin).read_text()
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
```

- [ ] **Step 4 : lancer le test et vérifier le succès**

Run: `python3 -m pytest tests/test_tls.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5 : commit**

```bash
git add phototheque/tls.py tests/test_tls.py
git commit -m "feat(tls): empreinte SHA-256 du certificat pour l'epinglage"
```

---

## Task 2 : configuration du transport

**Files:**
- Modify: `phototheque/config.py`
- Test: `tests/test_serve_config.py`

**Interfaces:**
- Consumes: rien.
- Produces: `config.CERT_FILE: Path`, `config.KEY_FILE: Path`,
  `config.PUBLIC_URL: str` désormais en `https` par défaut.

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_serve_config.py  (ajouter à la fin)


def test_chemins_du_certificat_par_defaut(monkeypatch):
    """Certificat et clé vivent dans ~/.config/phototheque/."""
    import importlib
    from pathlib import Path
    monkeypatch.delenv("CERT_FILE", raising=False)
    monkeypatch.delenv("KEY_FILE", raising=False)
    cfg = importlib.reload(importlib.import_module("phototheque.config"))
    assert cfg.CERT_FILE == Path.home() / ".config" / "phototheque" / "cert.pem"
    assert cfg.KEY_FILE == Path.home() / ".config" / "phototheque" / "key.pem"


def test_public_url_est_en_https(monkeypatch):
    """L'adresse publiée dans le QR passe en HTTPS (issue #3)."""
    import importlib, socket
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(socket, "gethostname", lambda: "ESSAI-HOTE")
    cfg = importlib.reload(importlib.import_module("phototheque.config"))
    assert cfg.PUBLIC_URL == "https://ESSAI-HOTE.local:8787"
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_serve_config.py -q`
Expected: FAIL — `AttributeError: module 'phototheque.config' has no attribute 'CERT_FILE'`,
puis `assert 'http://…' == 'https://…'`

- [ ] **Step 3 : modifier la configuration**

Dans `phototheque/config.py`, ajouter après `DEVICES_DB` :

```python
# Secrets et certificat du service. Dossier créé par deploy/install.sh en 0700,
# fichiers en 0600 : la clé privée ne doit être lisible que par le service.
CONFIG_DIR: Path = Path(os.environ.get(
    "CONFIG_DIR", str(Path.home() / ".config" / "phototheque")))
CERT_FILE: Path = Path(os.environ.get("CERT_FILE", str(CONFIG_DIR / "cert.pem")))
KEY_FILE: Path = Path(os.environ.get("KEY_FILE", str(CONFIG_DIR / "key.pem")))
ADMIN_FILE: Path = Path(os.environ.get("ADMIN_FILE", str(CONFIG_DIR / "admin")))
```

Puis remplacer le défaut de `PUBLIC_URL` :

```python
PUBLIC_URL: str = os.environ.get(
    "PUBLIC_URL", f"https://{socket.gethostname()}.local:{PORT}"
)
```

- [ ] **Step 4 : lancer toute la suite**

Run: `python3 -m pytest -q`
Expected: PASS. Le test `test_pair_page_publishes_a_reachable_url` passe
`PUBLIC_URL` explicitement, il n'est pas affecté.

- [ ] **Step 5 : commit**

```bash
git add phototheque/config.py tests/test_serve_config.py
git commit -m "feat(config): chemins du certificat et URL publiee en https"
```

---

## Task 3 : l'empreinte voyage dans le QR

**Files:**
- Modify: `phototheque/app.py` (route `/pair`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `tls.empreinte_certificat`, `config.CERT_FILE`.
- Produces: le QR encode `{"url", "token", "cert_sha256"}`, `cert_sha256`
  valant `None` quand aucun certificat n'est présent (service lancé à la main
  en HTTP pendant le développement).

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_app.py  (ajouter à la fin)


def test_pair_qr_transporte_l_empreinte_du_certificat(tmp_path, monkeypatch):
    """Le QR porte l'empreinte que l'application épinglera (issue #3)."""
    import json
    import subprocess
    from phototheque import tls

    cert = tmp_path / "cert.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-subj", "/CN=essai.local", "-keyout", str(tmp_path / "key.pem"),
         "-out", str(cert)],
        check=True, capture_output=True)
    monkeypatch.setenv("CERT_FILE", str(cert))

    a, client = _client(tmp_path, monkeypatch)
    charge = json.loads(a.charge_appairage())

    assert charge["cert_sha256"] == tls.empreinte_certificat(cert)


def test_pair_sans_certificat_ne_casse_pas(tmp_path, monkeypatch):
    """Service lancé à la main en HTTP : pas de certificat, pas d'empreinte."""
    import json
    monkeypatch.setenv("CERT_FILE", str(tmp_path / "absent.pem"))
    a, client = _client(tmp_path, monkeypatch)

    charge = json.loads(a.charge_appairage())

    assert charge["cert_sha256"] is None
    assert client.get("/pair").status_code == 200
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_app.py -q -k empreinte_du_certificat`
Expected: FAIL — `AttributeError: module 'phototheque.app' has no attribute 'charge_appairage'`

- [ ] **Step 3 : extraire la charge d'appairage et y mettre l'empreinte**

Dans `phototheque/app.py`, ajouter l'import `from . import tls` puis, avant la
route `/pair` :

```python
def _empreinte_du_certificat():
    """Empreinte du certificat servi, ou None s'il n'y en a pas.

    Absent = service lancé à la main en HTTP pour du développement. On ne
    casse pas la page d'appairage pour autant ; l'application saura que le
    serveur n'est pas épinglable.
    """
    try:
        return tls.empreinte_certificat(config.CERT_FILE)
    except OSError:
        return None


def charge_appairage() -> str:
    """Le JSON encodé dans le QR : où joindre le serveur, jeton, empreinte."""
    _, secret = _appairage_en_cours
    return json.dumps(pairing.pairing_payload(
        config.PUBLIC_URL, secret, _empreinte_du_certificat()))
```

Puis, dans la route `/pair`, remplacer les deux lignes qui construisaient la
charge par :

```python
    return web.pair_html(pairing.qr_svg(charge_appairage()), config.PUBLIC_URL)
```

(la variable locale `url` et l'appel direct à `pairing.pairing_payload`
disparaissent).

- [ ] **Step 4 : lancer toute la suite**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 5 : vérifier que le QR reste lisible**

L'empreinte ajoute 64 caractères : le QR devient plus dense. Générer une image
et **la regarder** — ce défaut ne se voit pas autrement :

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from phototheque import pairing
import json
charge = json.dumps({'url':'https://IZQUIERDO-NUC.local:8787',
                     'token':'x'*43, 'cert_sha256':'a'*64})
print('charge :', len(charge), 'caracteres')
open('/tmp/qr.html','w').write('<body style=background:#fff>'+pairing.qr_svg(charge))
"
```

Ouvrir `/tmp/qr.html`, vérifier que les modules restent nets. Si le QR paraît
trop dense, augmenter la taille par défaut dans `pairing.qr_svg` (`taille=360`)
et ajuster `test_qr_svg_is_scalable_and_sized_for_screen`.

- [ ] **Step 6 : commit**

```bash
git add phototheque/app.py tests/test_app.py
git commit -m "feat(pairing): transmettre l'empreinte du certificat dans le QR"
```

---

## Task 4 : servir en HTTPS

**Files:**
- Modify: `deploy/phototheque.service`
- Modify: `deploy/install.sh`
- Modify: `deploy/lib.sh`
- Test: `tests/test_deploy.py`

**Interfaces:**
- Consumes: `config.CERT_FILE`, `config.KEY_FILE`.
- Produces: `lib.sh::certificat_present <cert> <cle>` — vrai si les **deux**
  fichiers existent.

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_deploy.py  (ajouter à la fin)


def test_certificat_present_exige_les_deux_fichiers(tmp_path):
    """Un certificat sans sa clé est inutilisable : c'est « absent »."""
    cert, cle = tmp_path / "cert.pem", tmp_path / "key.pem"
    code, _ = appeler("certificat_present", cert, cle)
    assert code == 1                      # aucun des deux

    cert.write_text("x")
    code, _ = appeler("certificat_present", cert, cle)
    assert code == 1                      # la clé manque

    cle.write_text("x")
    code, _ = appeler("certificat_present", cert, cle)
    assert code == 0                      # les deux


def test_l_unite_systemd_sert_en_https():
    """L'unité passe le certificat à uvicorn."""
    unite = (LIB.parent / "phototheque.service").read_text()
    assert "--ssl-keyfile" in unite and "--ssl-certfile" in unite
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_deploy.py -q -k "certificat or https"`
Expected: FAIL — `certificat_present: command not found`, puis
`assert '--ssl-keyfile' in …`

- [ ] **Step 3 : ajouter la fonction de décision**

Dans `deploy/lib.sh`, à la fin :

```bash
certificat_present() {
    # Vrai si le certificat ET sa clé existent. L'un sans l'autre est
    # inutilisable : on considère alors qu'il n'y a pas de certificat, et
    # install.sh en fabriquera un.
    [ -f "$1" ] && [ -f "$2" ]
}
```

- [ ] **Step 4 : modifier l'unité systemd**

Dans `deploy/phototheque.service`, remplacer la ligne `ExecStart` par :

```
ExecStart=/home/izquierdo/.venv-server/bin/uvicorn phototheque.app:app \
    --host 0.0.0.0 --port 8787 \
    --ssl-keyfile /home/izquierdo/.config/phototheque/key.pem \
    --ssl-certfile /home/izquierdo/.config/phototheque/cert.pem
```

- [ ] **Step 5 : fabriquer le certificat dans install.sh**

Dans `deploy/install.sh`, ajouter juste après l'étape « Environnement Python »,
et renuméroter les étapes suivantes (le total passe de 7 à 9) :

```bash
# --------------------------------------------------------------------------
etape "3/9  Certificat du serveur"

CONFIG_DIR="$HOME/.config/phototheque"
CERT="$CONFIG_DIR/cert.pem"
CLE="$CONFIG_DIR/key.pem"
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

if certificat_present "$CERT" "$CLE"; then
    info "certificat déjà en place, conservé"
    info "empreinte : $("$PYTHON" -c "
import sys; sys.path.insert(0, '$racine')
from phototheque import tls
print(tls.empreinte_certificat('$CERT'))")"
else
    # L'adresse du NUC, pour que joindre le service par son IP n'ajoute pas
    # une seconde erreur au navigateur.
    IP=$(hostname -I | awk '{print $1}')
    info "fabrication d'un certificat auto-signé (10 ans)"
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -subj "/CN=$(hostname).local" \
        -addext "subjectAltName=DNS:$(hostname).local,DNS:localhost,IP:${IP},IP:127.0.0.1" \
        -keyout "$CLE" -out "$CERT" 2>/dev/null
    chmod 600 "$CLE"
    info "certificat créé"
fi
```

> **Ne jamais régénérer un certificat existant.** Son empreinte changerait et
> tous les téléphones appairés seraient rejetés — il faudrait tous les
> réappairer.

- [ ] **Step 6 : passer le test de fumée en HTTPS**

Dans `deploy/install.sh`, remplacer `http://127.0.0.1` par `https://127.0.0.1`
dans `service_repond()` **et** dans le bloc de vérification final, et désactiver
la vérification du certificat (il est auto-signé) :

```python
import ssl, sys, urllib.request
contexte = ssl._create_unverified_context()   # certificat auto-signé, attendu
urllib.request.urlopen("https://127.0.0.1:%s/" % sys.argv[1],
                       timeout=2, context=contexte)
```

Le même `contexte` est passé à chaque `urlopen` du bloc de vérification.

- [ ] **Step 7 : afficher la bonne adresse à la fin**

Dans le résumé final de `install.sh`, remplacer `http://` par `https://` :

```bash
info "admin     : https://$(hostname).local:${PORT}/"
info "appairage : https://$(hostname).local:${PORT}/pair"
info "ATTENTION : le navigateur avertira au premier accès (certificat"
info "            auto-signé). Accepter une fois par appareil."
```

- [ ] **Step 8 : vérifier**

```bash
bash -n deploy/install.sh && shellcheck deploy/install.sh deploy/lib.sh
python3 -m pytest -q
```
Expected: syntaxe OK, shellcheck propre, suite verte.

- [ ] **Step 9 : commit**

```bash
git add deploy/ tests/test_deploy.py
git commit -m "feat(deploy): servir en HTTPS avec un certificat auto-signe (closes #3)"
```

---

## Task 5 : empreinte et vérification du mot de passe admin

**Files:**
- Create: `phototheque/adminauth.py`
- Test: `tests/test_adminauth.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `adminauth.empreinte(mot_de_passe: str, iterations: int = ITERATIONS) -> str`
    → `"pbkdf2_sha256$<iterations>$<sel hex>$<empreinte hex>"`
  - `adminauth.verifier(mot_de_passe: str, enregistre: str) -> bool`
  - `adminauth.ITERATIONS: int`

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_adminauth.py
"""Tests du mot de passe d'administration (issue #10)."""

from phototheque import adminauth


def test_le_mot_de_passe_n_est_pas_stocke_en_clair():
    enregistre = adminauth.empreinte("correct-cheval-pile-agrafe")
    assert "correct-cheval-pile-agrafe" not in enregistre


def test_format_enregistre():
    """Le format porte ses paramètres : on pourra durcir sans tout casser."""
    enregistre = adminauth.empreinte("secret")
    algo, iterations, sel, empreinte = enregistre.split("$")
    assert algo == "pbkdf2_sha256"
    assert int(iterations) >= 100_000
    assert len(sel) == 32 and len(empreinte) == 64


def test_le_bon_mot_de_passe_est_accepte():
    enregistre = adminauth.empreinte("secret")
    assert adminauth.verifier("secret", enregistre) is True


def test_un_mauvais_mot_de_passe_est_refuse():
    enregistre = adminauth.empreinte("secret")
    assert adminauth.verifier("Secret", enregistre) is False
    assert adminauth.verifier("", enregistre) is False


def test_deux_empreintes_du_meme_mot_de_passe_different():
    """Sel aléatoire : deux installations n'ont pas la même empreinte."""
    assert adminauth.empreinte("secret") != adminauth.empreinte("secret")


def test_un_enregistrement_illisible_refuse_tout():
    """Fichier tronqué ou corrompu : on refuse, on ne laisse pas passer."""
    for mauvais in ("", "n'importe quoi", "pbkdf2_sha256$abc$def", "a$b$c$d"):
        assert adminauth.verifier("secret", mauvais) is False
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_adminauth.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'phototheque.adminauth'`

- [ ] **Step 3 : écrire le module**

```python
# phototheque/adminauth.py
"""Mot de passe d'administration : empreinte et vérification.

Le mot de passe n'est jamais enregistré en clair. On stocke une empreinte
lente à calculer : une tentative coûte quelques dizaines de millisecondes au
serveur, ce qui rend une attaque par essais successifs inopérante sur un
réseau local, sans gêner la navigation.

Rien d'autre que la bibliothèque standard : le module `cryptography` est
absent du venv du NUC et doit le rester.
"""

import hashlib
import hmac
import secrets

# Ajusté à l'installation pour coûter environ 100 ms sur le NUC (2 cœurs).
ITERATIONS = 240_000
ALGO = "pbkdf2_sha256"


def empreinte(mot_de_passe: str, iterations: int = ITERATIONS) -> str:
    """Renvoie « pbkdf2_sha256$<itérations>$<sel>$<empreinte> ».

    Le sel est tiré au hasard : deux installations avec le même mot de passe
    n'ont pas la même empreinte. Le nombre d'itérations est stocké avec, pour
    pouvoir le durcir plus tard sans invalider les mots de passe existants.
    """
    sel = secrets.token_bytes(16)
    brut = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel, iterations)
    return f"{ALGO}${iterations}${sel.hex()}${brut.hex()}"


def verifier(mot_de_passe: str, enregistre: str) -> bool:
    """Vrai si le mot de passe correspond à l'empreinte enregistrée.

    Un enregistrement illisible (fichier tronqué, format inconnu) fait
    échouer la vérification : en cas de doute on refuse, on ne laisse pas
    passer.
    """
    try:
        algo, iterations, sel_hex, attendu_hex = enregistre.split("$")
        if algo != ALGO:
            return False
        brut = hashlib.pbkdf2_hmac(
            "sha256", mot_de_passe.encode(), bytes.fromhex(sel_hex), int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    # Comparaison en temps constant : la durée de la réponse ne doit pas
    # révéler combien de caractères sont corrects.
    return hmac.compare_digest(brut.hex(), attendu_hex)
```

- [ ] **Step 4 : lancer le test et vérifier le succès**

Run: `python3 -m pytest tests/test_adminauth.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5 : mesurer le coût sur le NUC**

```bash
rsync -a --delete --exclude .git --exclude __pycache__ ./ izquierdo@192.168.1.21:~/mesure/
ssh izquierdo@192.168.1.21 'cd ~/mesure && ~/.venv-server/bin/python -c "
import sys, time; sys.path.insert(0, \".\")
from phototheque import adminauth
e = adminauth.empreinte(\"essai\")
t = time.time(); adminauth.verifier(\"essai\", e)
print(\"%.0f ms par verification\" % ((time.time()-t)*1000))"; rm -rf ~/mesure'
```

Viser **80 à 150 ms**. Ajuster `ITERATIONS` et relancer si on sort de la plage.
Reporter la valeur mesurée dans le message de commit.

- [ ] **Step 6 : commit**

```bash
git add phototheque/adminauth.py tests/test_adminauth.py
git commit -m "feat(admin): empreinte pbkdf2 du mot de passe d'administration"
```

---

## Task 6 : protéger la surface d'administration

**Files:**
- Modify: `phototheque/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `adminauth.verifier`, `config.ADMIN_FILE`.
- Produces: `app.require_admin` — dépendance FastAPI ; renvoie `401` avec
  `WWW-Authenticate: Basic realm="phototheque"` si l'authentification manque
  ou échoue, **et aussi si le fichier de mot de passe est absent**.

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_app.py  (ajouter à la fin)

ADRESSES_ADMIN = ["/", "/pair", "/devices"]


def _avec_admin(tmp_path, monkeypatch, mot_de_passe="secret-admin"):
    """Installe un mot de passe admin et renvoie l'en-tête correspondant."""
    import base64
    from phototheque import adminauth
    fichier = tmp_path / "admin"
    fichier.write_text(adminauth.empreinte(mot_de_passe, iterations=1000))
    monkeypatch.setenv("ADMIN_FILE", str(fichier))
    jeton = base64.b64encode(f"admin:{mot_de_passe}".encode()).decode()
    return {"Authorization": f"Basic {jeton}"}


@pytest.mark.parametrize("adresse", ADRESSES_ADMIN)
def test_les_adresses_d_admin_exigent_un_mot_de_passe(adresse, tmp_path, monkeypatch):
    """Un test par adresse : ajouter une route non protégée casse la suite."""
    _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    r = client.get(adresse)
    assert r.status_code == 401, adresse
    assert "Basic" in r.headers.get("WWW-Authenticate", ""), adresse


def test_revocation_exige_un_mot_de_passe(tmp_path, monkeypatch):
    _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    assert client.post("/devices/peu-importe/revoke").status_code == 401


@pytest.mark.parametrize("adresse", ADRESSES_ADMIN)
def test_le_bon_mot_de_passe_ouvre_l_admin(adresse, tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    assert client.get(adresse, headers=entetes).status_code == 200, adresse


def test_un_mauvais_mot_de_passe_est_refuse(tmp_path, monkeypatch):
    import base64
    _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    faux = base64.b64encode(b"admin:pas-le-bon").decode()
    r = client.get("/", headers={"Authorization": f"Basic {faux}"})
    assert r.status_code == 401


def test_sans_fichier_de_mot_de_passe_l_admin_est_fermee(tmp_path, monkeypatch):
    """Pas encore installé : on refuse plutôt que d'ouvrir en grand."""
    monkeypatch.setenv("ADMIN_FILE", str(tmp_path / "jamais-cree"))
    a, client = _client(tmp_path, monkeypatch)
    assert client.get("/").status_code == 401
```

Ajouter `import pytest` en tête de `tests/test_app.py`.

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_app.py -q -k admin`
Expected: FAIL — les adresses répondent `200` sans authentification.

- [ ] **Step 3 : écrire la dépendance et l'appliquer**

Dans `phototheque/app.py`, ajouter `import base64` et `from . import adminauth`,
puis après `require_device` :

```python
def require_admin(authorization: str = Header(default="")) -> None:
    """Dépendance d'auth admin : « Authorization: Basic <utilisateur:secret> ».

    Le navigateur affiche sa propre fenêtre de connexion dès qu'on répond 401
    avec l'en-tête WWW-Authenticate. Sans cet en-tête il n'affiche rien.

    Un fichier de mot de passe absent ferme l'administration : le service n'a
    pas encore été installé par deploy/install.sh, mieux vaut refuser que
    laisser la surface ouverte.
    """
    refus = HTTPException(
        status_code=401, detail="authentification requise",
        headers={"WWW-Authenticate": 'Basic realm="phototheque"'},
    )
    try:
        enregistre = config.ADMIN_FILE.read_text().strip()
    except OSError:
        raise refus
    prefixe = "Basic "
    if not authorization.startswith(prefixe):
        raise refus
    try:
        identifiants = base64.b64decode(authorization[len(prefixe):]).decode()
        utilisateur, _, secret = identifiants.partition(":")
    except (ValueError, UnicodeDecodeError):
        raise refus
    if utilisateur != "admin" or not adminauth.verifier(secret, enregistre):
        raise refus
```

Puis ajouter `_: None = Depends(require_admin)` aux quatre routes concernées :

```python
@app.get("/devices")
def list_devices(_: None = Depends(require_admin)) -> list:

@app.post("/devices/{device_id}/revoke")
def revoke_device(device_id: str, _: None = Depends(require_admin)) -> dict:

@app.get("/pair", response_class=HTMLResponse)
def pair(_: None = Depends(require_admin)) -> str:

@app.get("/", response_class=HTMLResponse)
def admin(_: None = Depends(require_admin)) -> str:
```

- [ ] **Step 4 : réparer les tests existants**

Les tests qui appelaient `/`, `/pair` ou `/devices` sans authentification vont
échouer — c'est le comportement voulu. Ajouter `_avec_admin(...)` avant
`_client(...)` et passer `headers=entetes` dans ces tests :
`test_pair_page_creates_device_and_qr`, `test_pair_page_purges_stale_pairings`,
`test_admin_page_renders`, `test_list_and_revoke_device`,
`test_pair_page_reuses_the_same_qr_while_valid`,
`test_pair_page_issues_a_new_qr_once_the_previous_is_used`,
`test_pair_page_publishes_a_reachable_url`,
`test_pair_qr_transporte_l_empreinte_du_certificat`,
`test_pair_sans_certificat_ne_casse_pas`.

- [ ] **Step 5 : lancer toute la suite**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 6 : commit**

```bash
git add phototheque/app.py tests/test_app.py
git commit -m "feat(admin): mot de passe sur /, /pair, /devices et revocation (closes #10)"
```

---

## Task 7 : générer le mot de passe à l'installation

**Files:**
- Modify: `deploy/install.sh`
- Test: `tests/test_deploy.py`

**Interfaces:**
- Consumes: `adminauth.empreinte`.
- Produces: `~/.config/phototheque/admin` en `0600`, mot de passe affiché une
  seule fois.

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_deploy.py  (ajouter à la fin)


def test_install_ne_regenere_jamais_un_secret_existant():
    """Régénérer le mot de passe ou le certificat casserait l'existant."""
    script = "\n".join(_lignes_de_code(LIB.parent / "install.sh"))
    # Les deux créations sont gardées par un test d'existence.
    assert "certificat_present" in script
    assert "[ -f \"$ADMIN\" ]" in script or "-f \"$ADMIN\"" in script
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_deploy.py -q -k regenere`
Expected: FAIL — `assert '-f "$ADMIN"' in script`

- [ ] **Step 3 : ajouter l'étape dans install.sh**

Juste après l'étape du certificat :

```bash
# --------------------------------------------------------------------------
etape "4/9  Mot de passe d'administration"

ADMIN="$CONFIG_DIR/admin"
if [ -f "$ADMIN" ]; then
    info "mot de passe déjà défini, conservé"
    info "(pour en changer : rm $ADMIN puis relancer ce script)"
else
    MOT_DE_PASSE=$("$PYTHON" -c "import secrets; print(secrets.token_urlsafe(12))")
    "$PYTHON" -c "
import sys; sys.path.insert(0, '$racine')
from phototheque import adminauth
print(adminauth.empreinte('$MOT_DE_PASSE'))" > "$ADMIN"
    chmod 600 "$ADMIN"
    printf '\n\033[1m    ┌─────────────────────────────────────────────┐\033[0m\n'
    printf '\033[1m    │  Identifiants d'"'"'administration              │\033[0m\n'
    printf '\033[1m    │  utilisateur : admin                        │\033[0m\n'
    printf '\033[1m    │  mot de passe : %-27s │\033[0m\n' "$MOT_DE_PASSE"
    printf '\033[1m    └─────────────────────────────────────────────┘\033[0m\n'
    info "NOTE-LE MAINTENANT : il ne sera plus jamais affiché."
    printf '\n'
fi
```

- [ ] **Step 4 : vérifier**

```bash
bash -n deploy/install.sh && shellcheck deploy/install.sh
python3 -m pytest -q
```
Expected: syntaxe OK, shellcheck propre, suite verte.

- [ ] **Step 5 : commit**

```bash
git add deploy/install.sh tests/test_deploy.py
git commit -m "feat(deploy): generer le mot de passe d'administration a l'installation"
```

---

## Task 8 : horizons par appareil et par dossier

**Files:**
- Modify: `phototheque/devices.py`
- Test: `tests/test_devices.py`

**Interfaces:**
- Consumes: rien.
- Produces, sur `DeviceStore` :
  - `set_horizon_initial(device_id: str, date_iso: str) -> None`
  - `get_horizon_initial(device_id: str) -> str | None`
  - `set_horizon(device_id: str, dossier: str, ts: float) -> None`
  - `get_horizons(device_id: str) -> dict[str, float]`

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_devices.py  (ajouter à la fin)


def test_horizon_initial_aller_retour():
    st = DeviceStore(":memory:")
    dev_id, _ = st.pair("Pixel")
    assert st.get_horizon_initial(dev_id) is None
    st.set_horizon_initial(dev_id, "2026-09-17")
    assert st.get_horizon_initial(dev_id) == "2026-09-17"
    st.close()


def test_les_horizons_sont_propres_a_chaque_appareil():
    """Deux téléphones ne doivent pas partager le même horizon."""
    st = DeviceStore(":memory:")
    a, _ = st.pair("Pixel")
    b, _ = st.pair("Tablette")
    st.set_horizon(a, "DCIM/Camera", 1000.0)
    st.set_horizon(b, "DCIM/Camera", 2000.0)
    assert st.get_horizons(a) == {"DCIM/Camera": 1000.0}
    assert st.get_horizons(b) == {"DCIM/Camera": 2000.0}
    st.close()


def test_les_horizons_sont_propres_a_chaque_dossier():
    st = DeviceStore(":memory:")
    dev_id, _ = st.pair("Pixel")
    st.set_horizon(dev_id, "DCIM/Camera", 1000.0)
    st.set_horizon(dev_id, "Movies", 2000.0)
    assert st.get_horizons(dev_id) == {"DCIM/Camera": 1000.0, "Movies": 2000.0}
    st.close()


def test_un_horizon_ecrase_le_precedent():
    st = DeviceStore(":memory:")
    dev_id, _ = st.pair("Pixel")
    st.set_horizon(dev_id, "DCIM/Camera", 1000.0)
    st.set_horizon(dev_id, "DCIM/Camera", 3000.0)
    assert st.get_horizons(dev_id) == {"DCIM/Camera": 3000.0}
    st.close()


def test_migration_d_une_base_sans_horizons(tmp_path):
    """Une base d'avant ce lot s'ouvre sans perdre ses appareils."""
    import sqlite3
    from phototheque.devices import _hash
    db = tmp_path / "ancienne.db"
    cx = sqlite3.connect(str(db))
    cx.execute("CREATE TABLE devices (id TEXT PRIMARY KEY, label TEXT,"
               " secret_hash TEXT UNIQUE, paired_at TEXT, confirmed_at TEXT)")
    cx.execute("INSERT INTO devices VALUES ('vieux','Pixel',?,"
               "'2026-01-01T10:00:00','2026-01-01T10:00:00')",
               (_hash("secret-historique"),))
    cx.commit(); cx.close()

    st = DeviceStore(db)

    assert st.validate("secret-historique") == "vieux"
    assert st.get_horizon_initial("vieux") is None   # aucune limite retroactive
    assert st.get_horizons("vieux") == {}
    st.close()
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_devices.py -q -k horizon`
Expected: FAIL — `AttributeError: 'DeviceStore' object has no attribute 'get_horizon_initial'`

- [ ] **Step 3 : étendre le schéma et ajouter les méthodes**

Dans `phototheque/devices.py`, `__init__` crée la nouvelle table :

```python
            self._cx.execute(
                "CREATE TABLE IF NOT EXISTS horizons ("
                " appareil TEXT NOT NULL, dossier TEXT NOT NULL,"
                " dernier_ts REAL NOT NULL, PRIMARY KEY (appareil, dossier))"
            )
```

Étendre `_migrer_confirmation` (renommée `_migrer`) :

```python
    def _migrer(self) -> None:
        """Ajoute les colonnes apparues après la création de la table.

        Les appareils déjà enregistrés sont considérés CONFIRMÉS : il est hors
        de question de déconnecter un téléphone qui fonctionne parce que le
        schéma a changé. Leur horizon initial reste NULL, c'est-à-dire aucune
        limite — on ne restreint pas rétroactivement ce qu'ils avaient le droit
        d'envoyer.
        """
        colonnes = {c[1] for c in self._cx.execute("PRAGMA table_info(devices)")}
        if "confirmed_at" not in colonnes:
            self._cx.execute("ALTER TABLE devices ADD COLUMN confirmed_at TEXT")
            self._cx.execute("UPDATE devices SET confirmed_at = paired_at")
        if "horizon_initial" not in colonnes:
            self._cx.execute("ALTER TABLE devices ADD COLUMN horizon_initial TEXT")
```

Ajouter les quatre méthodes :

```python
    def set_horizon_initial(self, device_id: str, date_iso: str) -> None:
        """Date à partir de laquelle cet appareil remonte ses médias.

        Choisie à l'appairage. Sert de repli pour les dossiers dont on ne
        connaît pas encore d'horizon.
        """
        with self._lock:
            self._cx.execute(
                "UPDATE devices SET horizon_initial=? WHERE id=?", (date_iso, device_id)
            )
            self._cx.commit()

    def get_horizon_initial(self, device_id: str):
        with self._lock:
            cur = self._cx.execute(
                "SELECT horizon_initial FROM devices WHERE id=?", (device_id,)
            )
            ligne = cur.fetchone()
        return ligne[0] if ligne else None

    def set_horizon(self, device_id: str, dossier: str, ts: float) -> None:
        """Enregistre jusqu'où ce dossier a été synchronisé pour cet appareil."""
        with self._lock:
            self._cx.execute(
                "INSERT INTO horizons (appareil, dossier, dernier_ts) VALUES (?,?,?)"
                " ON CONFLICT(appareil, dossier) DO UPDATE SET dernier_ts=excluded.dernier_ts",
                (device_id, dossier, ts),
            )
            self._cx.commit()

    def get_horizons(self, device_id: str) -> dict:
        """Les horizons connus de cet appareil, par dossier."""
        with self._lock:
            lignes = self._cx.execute(
                "SELECT dossier, dernier_ts FROM horizons WHERE appareil=?", (device_id,)
            ).fetchall()
        return {dossier: ts for dossier, ts in lignes}
```

Remplacer l'appel `self._migrer_confirmation()` par `self._migrer()`.

- [ ] **Step 4 : lancer toute la suite**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 5 : commit**

```bash
git add phototheque/devices.py tests/test_devices.py
git commit -m "feat(devices): horizons de synchro par (appareil, dossier)"
```

---

## Task 9 : choisir la date à l'appairage

**Files:**
- Modify: `phototheque/web.py`, `phototheque/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `DeviceStore.set_horizon_initial`, `get_horizon_initial`.
- Produces: `POST /pair` (champ de formulaire `depuis`, format `AAAA-MM-JJ`) ;
  `web.pair_html(qr_svg, url, depuis)` gagne un troisième paramètre.

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_app.py  (ajouter à la fin)


def test_la_page_d_appairage_propose_une_date(tmp_path, monkeypatch):
    """Par défaut aujourd'hui : on ne remonte pas tout l'historique."""
    import datetime
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    r = client.get("/pair", headers=entetes)
    assert 'name="depuis"' in r.text
    assert datetime.date.today().isoformat() in r.text


def test_poster_une_date_l_enregistre_sur_l_appairage(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/pair", headers=entetes)
    dev_id = a.devices().list()[0]["id"]

    r = client.post("/pair", headers=entetes, data={"depuis": "2020-01-01"})

    assert r.status_code == 200
    assert a.devices().get_horizon_initial(dev_id) == "2020-01-01"
    assert "2020-01-01" in r.text


def test_une_date_invalide_est_refusee(tmp_path, monkeypatch):
    entetes = _avec_admin(tmp_path, monkeypatch)
    a, client = _client(tmp_path, monkeypatch)
    client.get("/pair", headers=entetes)
    assert client.post("/pair", headers=entetes,
                       data={"depuis": "hier"}).status_code == 400
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_app.py -q -k appairage_propose`
Expected: FAIL — `assert 'name="depuis"' in …`

- [ ] **Step 3 : ajouter le champ à la page**

Dans `phototheque/web.py`, `pair_html` gagne un paramètre et un formulaire :

```python
def pair_html(qr_svg: str, url: str, depuis: str) -> str:
    """Page d'appairage : le QR, l'adresse en secours, et la date de départ."""
    corps = (
        '<div class="centre">'
        "<header><h1>Appairer un téléphone</h1>"
        '<p class="hote">Scanne ce code avec l\'application</p></header>'
        f'<div class="cadre-qr">{qr_svg}</div>'
        '<div class="carte" style="margin-top:24px">'
        '<form method="post" action="/pair">'
        '<div class="detail">Importer les médias à partir du :</div>'
        f'<input type="date" name="depuis" value="{depuis}">'
        '<button type="submit">Enregistrer</button>'
        '</form>'
        f"<div class=\"detail\">Ou saisis l'adresse à la main :<br><code>{url}</code></div>"
        '<div class="detail" style="margin-top:10px;color:var(--muted)">'
        "Ce code reste valable 10 minutes. Il devient définitif dès que le "
        "téléphone s'en sert, et se renouvelle sinon.</div>"
        "</div>"
        '<p style="margin-top:24px"><a class="bouton" href="/">Retour</a></p>'
        "</div>"
    )
    return _document("phototheque — appairage", corps, STYLE_QR)
```

Ajouter au bloc `STYLE_QR` :

```css
form { margin: 0 0 14px; display: flex; gap: 8px; align-items: center; }
input[type=date] {
  font: inherit; padding: 6px 10px; border-radius: 9px;
  border: 1px solid var(--border); background: var(--plane); color: var(--ink);
}
```

- [ ] **Step 4 : ajouter la route POST**

Dans `phototheque/app.py`, ajouter `import datetime` et remplacer la route
`/pair` par :

```python
def _page_appairage() -> str:
    """Rend la page d'appairage pour l'appairage en cours."""
    identifiant, _ = _appairage_en_cours
    depuis = (devices().get_horizon_initial(identifiant)
              or datetime.date.today().isoformat())
    return web.pair_html(pairing.qr_svg(charge_appairage()),
                         config.PUBLIC_URL, depuis)


@app.get("/pair", response_class=HTMLResponse)
def pair(_: None = Depends(require_admin)) -> str:
    """Affiche le QR d'appairage. Un GET ne crée rien de nouveau.

    Recharger la page réaffiche le même QR tant qu'il est valable. Un
    appairage neuf n'est émis qu'une fois le précédent utilisé par un
    téléphone, expiré, ou révoqué.
    """
    global _appairage_en_cours
    devices().purge_pending()

    if _appairage_en_cours is not None:
        identifiant, _ = _appairage_en_cours
        if not devices().is_pending(identifiant):
            _appairage_en_cours = None      # confirmé, expiré ou révoqué
    if _appairage_en_cours is None:
        _appairage_en_cours = devices().pair("Nouveau téléphone")
    return _page_appairage()


@app.post("/pair", response_class=HTMLResponse)
def pair_depuis(depuis: str = Form(...), _: None = Depends(require_admin)) -> str:
    """Enregistre la date à partir de laquelle l'appareil remontera ses médias."""
    try:
        datetime.date.fromisoformat(depuis)
    except ValueError:
        raise HTTPException(status_code=400, detail="date invalide (AAAA-MM-JJ)")
    if _appairage_en_cours is None:
        raise HTTPException(status_code=409, detail="aucun appairage en cours")
    identifiant, _secret = _appairage_en_cours
    devices().set_horizon_initial(identifiant, depuis)
    return _page_appairage()
```

- [ ] **Step 5 : lancer toute la suite**

Run: `python3 -m pytest -q`
Expected: PASS. Le test `test_pair_html_keeps_the_qr_on_a_light_background`
appelle `pair_html` à deux arguments : lui passer une date.

- [ ] **Step 6 : regarder la page**

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from phototheque import web, pairing
open('/tmp/pair.html','w').write(
    web.pair_html(pairing.qr_svg('essai'), 'https://essai.local:8787', '2026-09-17'))"
chromium-browser --headless=new --no-sandbox --screenshot=/tmp/pair.png \
    --window-size=880,900 file:///tmp/pair.html
```

Vérifier que le champ de date et le bouton sont alignés et lisibles, en thème
clair comme en sombre.

- [ ] **Step 7 : commit**

```bash
git add phototheque/app.py phototheque/web.py tests/test_app.py
git commit -m "feat(pairing): choisir la date de depart a l'appairage"
```

---

## Task 10 : l'application demande son horizon

**Files:**
- Modify: `phototheque/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `DeviceStore.get_horizons`, `get_horizon_initial`.
- Produces: `GET /sync/horizon` (jeton d'appareil) →
  `{"depuis": str | None, "dossiers": {str: float}}`

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_app.py  (ajouter à la fin)


def test_horizon_exige_un_jeton_d_appareil(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    assert client.get("/sync/horizon").status_code == 401


def test_horizon_renvoie_la_date_d_appairage_au_premier_appel(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    a.devices().set_horizon_initial(dev_id, "2026-09-17")

    r = client.get("/sync/horizon", headers={"Authorization": f"Bearer {secret}"})

    assert r.status_code == 200
    assert r.json() == {"depuis": "2026-09-17", "dossiers": {}}


def test_horizon_renvoie_les_dossiers_deja_synchronises(tmp_path, monkeypatch):
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    a.devices().set_horizon(dev_id, "DCIM/Camera", 1726574400.0)

    r = client.get("/sync/horizon", headers={"Authorization": f"Bearer {secret}"})

    assert r.json()["dossiers"] == {"DCIM/Camera": 1726574400.0}
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_app.py -q -k horizon`
Expected: FAIL — `404 Not Found` sur `/sync/horizon`

- [ ] **Step 3 : ajouter la route**

Dans `phototheque/app.py`, à côté des autres routes `/sync` :

```python
@app.get("/sync/horizon")
def sync_horizon(dev_id: str = Depends(require_device)) -> dict:
    """Indique à l'application depuis quand remonter les médias.

    'dossiers' donne les horizons déjà atteints. Pour un dossier absent de
    cette liste, l'application utilise son propre .flagfile_timestamp s'il
    existe (il reprend là où run_backup.sh s'était arrêté), sinon 'depuis'.
    'depuis' vaut null pour un appareil appairé avant l'introduction de ce
    réglage : aucune limite.
    """
    store = devices()
    return {"depuis": store.get_horizon_initial(dev_id),
            "dossiers": store.get_horizons(dev_id)}
```

`require_device` renvoie déjà l'identifiant de l'appareil ; il suffit de le
nommer au lieu de l'ignorer.

- [ ] **Step 4 : lancer toute la suite**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 5 : commit**

```bash
git add phototheque/app.py tests/test_app.py
git commit -m "feat(sync): GET /sync/horizon, horizon par dossier"
```

---

## Task 11 : l'horizon avance après un commit réussi

**Files:**
- Modify: `phototheque/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `DeviceStore.set_horizon`.
- Produces: `CommitRequest` gagne `horizons: dict[str, float] = {}`.

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_app.py  (ajouter à la fin)


def test_le_commit_enregistre_les_horizons(tmp_path, monkeypatch):
    import datetime, hashlib, io
    import mediasort.dates as d
    monkeypatch.setattr(d, "date_from_metadata", lambda p: datetime.date(2023, 5, 26))
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    contenu = b"une photo"; empreinte = hashlib.sha256(contenu).hexdigest()
    session = client.post("/sync/plan", headers=h, json={"files": [
        {"path": "DCIM/Camera/a.jpg", "size": len(contenu), "hash": empreinte}]
    }).json()["session"]
    client.post("/sync/upload", headers=h,
                data={"session": session, "path": "DCIM/Camera/a.jpg"},
                files={"file": ("a.jpg", io.BytesIO(contenu), "image/jpeg")})

    r = client.post("/sync/commit", headers=h, json={
        "session": session, "horizons": {"DCIM/Camera": 1726574400.0}})

    assert r.status_code == 200
    assert a.devices().get_horizons(dev_id) == {"DCIM/Camera": 1726574400.0}


def test_un_commit_qui_echoue_ne_fait_pas_avancer_l_horizon(tmp_path, monkeypatch):
    """Session inconnue : l'horizon ne bouge pas, la prochaine synchro reprend."""
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")

    r = client.post("/sync/commit",
                    headers={"Authorization": f"Bearer {secret}"},
                    json={"session": "inexistante",
                          "horizons": {"DCIM/Camera": 1726574400.0}})

    assert r.status_code == 404
    assert a.devices().get_horizons(dev_id) == {}


def test_le_commit_sans_horizons_reste_accepte(tmp_path, monkeypatch):
    """Champ facultatif : un client qui ne l'envoie pas fonctionne toujours."""
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Pixel")
    r = client.post("/sync/commit", headers={"Authorization": f"Bearer {secret}"},
                    json={"session": "inexistante"})
    assert r.status_code == 404      # refusée pour la session, pas pour le format
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_app.py -q -k horizons`
Expected: FAIL — l'horizon reste vide après le commit.

- [ ] **Step 3 : accepter et enregistrer les horizons**

Dans `phototheque/app.py` :

```python
class CommitRequest(BaseModel):
    session: str
    # Jusqu'où chaque dossier a été parcouru par l'application. Facultatif :
    # un client qui ne l'envoie pas continue de fonctionner.
    horizons: dict[str, float] = {}
```

Puis dans `sync_commit`, après le tri et le nettoyage :

```python
@app.post("/sync/commit")
def sync_commit(req: CommitRequest, dev_id: str = Depends(require_device)) -> dict:
    session_dir = config.INCOMING_DIR / req.session
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="session inconnue")
    cat = Catalog(config.CATALOG_DB)
    try:
        bilan = ingest.sort_session(session_dir, config.LIBRARY_DIR, cat)
    finally:
        cat.close()
    sessions.cleanup(config.INCOMING_DIR, req.session)
    # L'horizon n'avance QU'APRÈS un tri réussi : si la synchro échoue en
    # route, la prochaine reprend depuis le dernier point sûr. On peut
    # reproposer deux fois les mêmes fichiers — l'anti-doublon les écarte —
    # mais on ne peut jamais en perdre.
    for dossier, ts in req.horizons.items():
        devices().set_horizon(dev_id, dossier, ts)
    return bilan
```

- [ ] **Step 4 : lancer toute la suite**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 5 : commit**

```bash
git add phototheque/app.py tests/test_app.py
git commit -m "feat(sync): avancer l'horizon apres un commit reussi (closes #2)"
```

---

## Task 12 : retirer la table `synchros` du catalogue

**Files:**
- Modify: `mediasort/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: rien.
- Produces: `Catalog` n'expose plus `get_last_sync` ni `set_last_sync`.

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_catalog.py
# Remplacer test_last_sync_roundtrip par :


def test_le_catalogue_ne_gere_plus_les_horizons():
    """L'horizon de synchro appartient aux appareils, pas au catalogue.

    La table synchros était clé par dossier seulement : deux téléphones
    auraient partagé le même horizon. Elle a déménagé dans DeviceStore,
    clé par (appareil, dossier). Ce test empêche de la réintroduire ici.
    """
    cat = Catalog(":memory:")
    assert not hasattr(cat, "get_last_sync")
    assert not hasattr(cat, "set_last_sync")
    cat.close()


def test_un_catalogue_existant_avec_synchros_s_ouvre_toujours(tmp_path):
    """Une base d'avant ce lot garde sa table : on ne touche pas à 44 669 lignes."""
    import sqlite3
    db = tmp_path / "ancien.db"
    cx = sqlite3.connect(str(db))
    cx.execute("CREATE TABLE medias (empreinte TEXT PRIMARY KEY, taille INTEGER,"
               " chemin TEXT, date_prise TEXT, source_date TEXT,"
               " date_import TEXT, signature TEXT)")
    cx.execute("CREATE TABLE synchros (dossier TEXT PRIMARY KEY, dernier_ts REAL)")
    cx.execute("INSERT INTO medias (empreinte, taille, chemin) VALUES ('h',1,'/a.jpg')")
    cx.commit(); cx.close()

    cat = Catalog(db)

    assert cat.count() == 1
    cat.close()
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_catalog.py -q -k horizons`
Expected: FAIL — `assert not hasattr(cat, 'get_last_sync')`

- [ ] **Step 3 : retirer le code mort**

Dans `mediasort/catalog.py`, supprimer :

- la création de la table dans `__init__` :

```python
        self._cx.execute(
            "CREATE TABLE IF NOT EXISTS synchros ("
            " dossier TEXT PRIMARY KEY, dernier_ts REAL)"
        )
```

- les deux méthodes `get_last_sync` et `set_last_sync`.

Mettre à jour la docstring du module :

```python
"""Catalogue SQLite : anti-doublon par empreinte de contenu."""
```

> Une table `synchros` déjà présente dans un catalogue existant est laissée
> telle quelle : vide, sans effet, et la supprimer toucherait une base de
> 44 669 lignes sans rien apporter.

- [ ] **Step 4 : lancer toute la suite**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 5 : commit**

```bash
git add mediasort/catalog.py tests/test_catalog.py
git commit -m "refactor(catalog): retirer la table synchros, remplacee par les horizons d'appareil"
```

---

## Task 13 : nom convivial annoncé sur le réseau

**Files:**
- Modify: `deploy/install.sh`, `deploy/avahi-phototheque.service`
- Test: `tests/test_deploy.py`

**Interfaces:**
- Consumes: rien.
- Produces: `~/.config/phototheque/nom` (facultatif) — son contenu remplace
  `phototheque sur %h` dans l'annonce mDNS.

- [ ] **Step 1 : écrire le test qui échoue**

```python
# tests/test_deploy.py  (ajouter à la fin)


def test_l_annonce_mdns_porte_un_nom_substituable():
    """install.sh doit pouvoir remplacer le nom affiché sur le réseau."""
    annonce = (LIB.parent / "avahi-phototheque.service").read_text()
    assert "NOM_AFFICHE" in annonce
    script = "\n".join(_lignes_de_code(LIB.parent / "install.sh"))
    assert "NOM_AFFICHE" in script
```

- [ ] **Step 2 : lancer le test et vérifier l'échec**

Run: `python3 -m pytest tests/test_deploy.py -q -k mdns`
Expected: FAIL — `assert 'NOM_AFFICHE' in annonce`

- [ ] **Step 3 : rendre le nom substituable**

Dans `deploy/avahi-phototheque.service` :

```xml
  <name replace-wildcards="yes">NOM_AFFICHE</name>
```

Dans `deploy/install.sh`, à l'étape d'installation d'Avahi, remplacer le `cp`
par :

```bash
# Nom affiché par l'application dans sa liste de serveurs. « %h » est le nom
# de la machine, un nom technique ; un nom convivial est plus parlant.
if [ -f "$CONFIG_DIR/nom" ]; then
    NOM_AFFICHE=$(head -1 "$CONFIG_DIR/nom")
else
    NOM_AFFICHE="phototheque sur %h"
fi
sed "s|NOM_AFFICHE|${NOM_AFFICHE}|" deploy/avahi-${SERVICE}.service \
    | sudo tee "$AVAHI" >/dev/null
info "annoncé sur le réseau sous : ${NOM_AFFICHE}"
```

- [ ] **Step 4 : vérifier**

```bash
bash -n deploy/install.sh && shellcheck deploy/install.sh
python3 -m pytest -q
```
Expected: syntaxe OK, shellcheck propre, suite verte.

- [ ] **Step 5 : commit**

```bash
git add deploy/ tests/test_deploy.py
git commit -m "feat(deploy): nom convivial annonce en mDNS"
```

---

## Task 14 : documentation

**Files:**
- Modify: `README.md`, `docs/DEPLOIEMENT.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces: aucune interface de code.

- [ ] **Step 1 : adresses et avertissement dans le README**

Remplacer les deux adresses de la section 3 :

```markdown
- `https://IZQUIERDO-NUC.local:8787/` — page d'administration
- `https://IZQUIERDO-NUC.local:8787/pair` — QR code d'appairage

> **Au premier accès, le navigateur affiche un avertissement de sécurité.**
> C'est normal : le certificat est fabriqué par le NUC lui-même, aucune
> autorité extérieure ne le garantit. Clique sur « Paramètres avancés » puis
> « Continuer ». À faire une fois par appareil.
>
> L'identifiant est `admin` et le mot de passe est affiché par
> `./deploy/install.sh` à la première installation. Pour en changer :
> `rm ~/.config/phototheque/admin` puis relancer le script.
```

- [ ] **Step 2 : section dédiée dans DEPLOIEMENT.md**

Ajouter avant « Consulter et dépanner » :

```markdown
## Le certificat et le mot de passe

`install.sh` fabrique les deux à la première installation, dans
`~/.config/phototheque/` :

| Fichier | Rôle | Si tu le supprimes |
|---|---|---|
| `cert.pem`, `key.pem` | certificat du serveur | un nouveau est fabriqué — **tous les téléphones appairés sont rejetés** et doivent être réappairés |
| `admin` | empreinte du mot de passe | un nouveau mot de passe est tiré et affiché |
| `nom` | nom affiché sur le réseau (facultatif) | retour à « phototheque sur <machine> » |

**Ne supprime jamais le certificat sans raison.** L'application épingle son
empreinte : la changer revient à changer d'identité aux yeux des téléphones.

### Migrer vers une autre machine

Le téléphone retrouve le serveur par le réseau, pas par son adresse : il cherche
le service `_phototheque._tcp` et reconnaît le bon au certificat. Deux façons de
déménager :

**Garder les appairages** — copier la configuration et les données :

```bash
scp -r ~/.config/phototheque nouvelle-machine:~/.config/
scp ~/mediasort_catalog.db ~/phototheque_devices.db nouvelle-machine:~/
```

Puis `./deploy/install.sh` sur la nouvelle machine. Les téléphones continuent de
fonctionner sans rien faire. Réserve : le certificat copié porte les noms de
l'ancienne machine, donc le navigateur redeviendra avertissant.

**Repartir propre** — ne rien copier, lancer `./deploy/install.sh`, puis
réappairer chaque téléphone avec un nouveau QR.
```

- [ ] **Step 3 : mettre à jour le point de reprise**

Dans `CLAUDE.md`, ajouter à l'état actuel :

```markdown
- ✅ **Transport chiffré + admin protégée + horizon de synchro** (issues #3, #10,
  #2) : HTTPS auto-signé épinglable par l'app, mot de passe admin sur `/`,
  `/pair`, `/devices` et la révocation, horizon par (appareil, dossier).
  Adresse : `https://IZQUIERDO-NUC.local:8787/`, identifiant `admin`.
```

Et dans les commandes utiles, remplacer les adresses `http://` par `https://`.

- [ ] **Step 4 : vérifier qu'aucune adresse http ne subsiste**

```bash
grep -rn "http://IZQUIERDO-NUC\|http://nuc.local" --include=*.md . | grep -v superpowers
```
Expected: aucune ligne.

- [ ] **Step 5 : commit**

```bash
git add README.md docs/DEPLOIEMENT.md CLAUDE.md
git commit -m "docs: https, mot de passe admin et procedure de migration"
```

---

## Task 15 : déploiement et vérification sur le NUC

**Files:** aucun — vérification uniquement.

- [ ] **Step 1 : déployer**

À lancer **par le mainteneur**, dans un vrai terminal (mot de passe sudo) :

```bash
cd ~/phone_camera_import && git pull && ./deploy/install.sh
```

Noter le mot de passe d'administration affiché.

- [ ] **Step 2 : vérifier le transport**

```bash
ssh izquierdo@192.168.1.21 'openssl s_client -connect 127.0.0.1:8787 \
    -servername $(hostname).local < /dev/null 2>/dev/null \
    | openssl x509 -noout -fingerprint -sha256'
```

Comparer à l'empreinte affichée par `install.sh` : elles doivent être identiques
(aux deux-points près).

- [ ] **Step 3 : vérifier l'authentification**

```bash
ssh izquierdo@192.168.1.21 '~/.venv-server/bin/python -c "
import ssl, urllib.request, urllib.error, base64
ctx = ssl._create_unverified_context()
for entetes, attendu in (({}, 401), ({\"Authorization\": \"Basic \" +
        base64.b64encode(b\"admin:LE_MOT_DE_PASSE\").decode()}, 200)):
    req = urllib.request.Request(\"https://127.0.0.1:8787/\", headers=entetes)
    try:
        code = urllib.request.urlopen(req, context=ctx, timeout=5).status
    except urllib.error.HTTPError as e:
        code = e.code
    print(code, \"attendu\", attendu, \"->\", \"ok\" if code == attendu else \"ECHEC\")"'
```

- [ ] **Step 4 : vérifier l'annonce réseau**

Depuis une autre machine du réseau :

```bash
avahi-browse -tpr _phototheque._tcp
```

Expected: une ligne `=` avec le nom affiché, l'hôte, l'IP et le port 8787.

- [ ] **Step 5 : regarder les deux pages**

Ouvrir `https://IZQUIERDO-NUC.local:8787/` dans un navigateur, accepter
l'avertissement, saisir `admin` et le mot de passe. Vérifier que la page d'admin
s'affiche, puis `/pair` : **le QR doit être net et scannable** malgré les 64
caractères d'empreinte ajoutés.

- [ ] **Step 6 : fermer les issues**

```bash
gh issue comment 3 --body "Fait : HTTPS auto-signé, empreinte épinglable transmise dans le QR. Voir docs/superpowers/specs/2026-09-17-transport-auth-horizon-design.md"
gh issue comment 10 --body "Fait : mot de passe admin sur /, /pair, /devices et la révocation."
gh issue comment 2 --body "Fait : horizon par (appareil, dossier), date choisie à l'appairage, .flagfile_timestamp respecté par l'app."
```

Les `closes #N` des commits se déclencheront à la fusion de `dev` dans `main`.

---

## Auto-revue (couverture de la spec)

| Section de la spec | Tâche(s) |
|---|---|
| §2 certificat, service, empreinte, configuration | 1, 2, 3, 4 |
| §2 défaut assumé (l'adresse `http` cesse) | 4 (message final), 14 (doc) |
| §3 mécanisme Basic, mot de passe, surface protégée | 5, 6, 7 |
| §4 modèle de données, protocole en trois temps | 8, 9, 10, 11 |
| §4 retrait de `synchros` | 12 |
| §5 découverte, nom configurable, migration | 13, 14 |
| §6 contrat de l'application | 3, 10, 11 (endpoints), 14 (doc) |
| §7 stratégie de test | intégrée à chaque tâche ; vérification visuelle en 3 et 9 |
| §8 déploiement et retour en arrière | 4, 14, 15 |

**Points de vigilance signalés aux exécutants :**

- Task 6 casse volontairement neuf tests existants. C'est le signe que la
  protection fonctionne ; les réparer fait partie de la tâche.
- Task 3 et Task 9 comportent une étape « regarder le résultat ». Elle n'est pas
  facultative : la densité du QR et l'alignement du champ de date ne se voient
  pas dans une assertion.
- Task 5 demande une mesure réelle sur le NUC avant de figer `ITERATIONS`.
