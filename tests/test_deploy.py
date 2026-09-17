"""Tests des décisions prises par le script de déploiement (deploy/lib.sh).

Pourquoi tester un script shell : le 17/09/2026, deux décisions de
`deploy/install.sh` se sont trompées en production et ont mis le service en
boucle de redémarrage. Les deux sont maintenant des fonctions isolées, sans
effet de bord, appelables depuis ces tests.
"""

import os
import sqlite3
import subprocess
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "deploy" / "lib.sh"
INSTALL = LIB.parent / "install.sh"
DEPOT = LIB.parent.parent


def appeler(fonction, *arguments):
    """Appelle une fonction de lib.sh et renvoie (code de sortie, sortie)."""
    script = f'set -euo pipefail; source "{LIB}"; {fonction} ' + " ".join(
        f'"{a}"' for a in arguments
    )
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def _base_appareils(chemin, nombre):
    """Fabrique une base d'appairage contenant 'nombre' appareils."""
    cx = sqlite3.connect(str(chemin))
    cx.execute("CREATE TABLE devices (id TEXT PRIMARY KEY, label TEXT,"
               " secret_hash TEXT, paired_at TEXT)")
    for i in range(nombre):
        cx.execute("INSERT INTO devices VALUES (?,?,?,?)",
                   (f"id{i}", "tel", "hash", "2026-09-17T10:00:00"))
    cx.commit()
    cx.close()


# --- unite_installee : la décision qui a laissé tourner l'ancien service ----

def test_unite_installee_vrai_si_le_fichier_existe(tmp_path):
    unite = tmp_path / "mediaserve.service"
    unite.write_text("[Unit]\n")
    code, _ = appeler("unite_installee", unite)
    assert code == 0


def test_unite_installee_faux_si_absent(tmp_path):
    code, _ = appeler("unite_installee", tmp_path / "rien.service")
    assert code == 1


def _lignes_de_code(chemin):
    """Les lignes du script hors commentaires (qui, eux, citent le piège)."""
    return [l for l in chemin.read_text().splitlines()
            if not l.lstrip().startswith("#")]


def test_aucune_decision_prise_depuis_un_pipeline():
    """Régression : sous `set -o pipefail`, `systemctl ... | grep -q` renvoyait
    141 (SIGPIPE, grep ferme le tuyau au premier résultat) même quand la
    correspondance existait. La décision était donc inversée et l'ancien
    service restait actif, tenant le port 8787."""
    for script in (LIB, LIB.parent / "install.sh"):
        code = "\n".join(_lignes_de_code(script))
        assert "| grep -q" not in code, f"{script.name} décide depuis un pipeline"


# --- nb_appareils et doit_reprendre : la décision qui a perdu l'appairage ---

def test_nb_appareils_zero_si_fichier_absent(tmp_path):
    code, sortie = appeler("nb_appareils", tmp_path / "absent.db")
    assert code == 0 and sortie == "0"


def test_nb_appareils_compte_les_lignes(tmp_path):
    base = tmp_path / "devices.db"
    _base_appareils(base, 3)
    code, sortie = appeler("nb_appareils", base)
    assert code == 0 and sortie == "3"


def test_nb_appareils_zero_si_base_sans_table(tmp_path):
    """Une base créée par un simple import du module n'a pas encore de table."""
    base = tmp_path / "vide.db"
    sqlite3.connect(str(base)).close()
    code, sortie = appeler("nb_appareils", base)
    assert code == 0 and sortie == "0"


def test_doit_reprendre_quand_la_nouvelle_base_est_vide(tmp_path):
    """Le cas qui a échoué : la nouvelle base existe mais elle est vide.

    Importer phototheque.app crée la base (DeviceStore est instancié au
    chargement du module) : un simple test d'existence conclut à tort que la
    reprise a déjà eu lieu.
    """
    ancienne, nouvelle = tmp_path / "a.db", tmp_path / "n.db"
    _base_appareils(ancienne, 5)
    _base_appareils(nouvelle, 0)  # créée vide par un import de passage
    code, _ = appeler("doit_reprendre", ancienne, nouvelle)
    assert code == 0


def test_doit_reprendre_quand_la_nouvelle_base_est_absente(tmp_path):
    ancienne, nouvelle = tmp_path / "a.db", tmp_path / "n.db"
    _base_appareils(ancienne, 2)
    code, _ = appeler("doit_reprendre", ancienne, nouvelle)
    assert code == 0


def test_ne_doit_pas_reprendre_si_la_nouvelle_base_est_peuplee(tmp_path):
    """Ne jamais écraser des appairages déjà en place."""
    ancienne, nouvelle = tmp_path / "a.db", tmp_path / "n.db"
    _base_appareils(ancienne, 2)
    _base_appareils(nouvelle, 7)
    code, _ = appeler("doit_reprendre", ancienne, nouvelle)
    assert code == 1


def test_ne_doit_pas_reprendre_si_ancienne_base_absente(tmp_path):
    """Première installation : il n'y a rien à reprendre."""
    code, _ = appeler("doit_reprendre", tmp_path / "a.db", tmp_path / "n.db")
    assert code == 1


# --- certificat_present et service HTTPS ------------------------------------

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


# --- fabrication du certificat dans install.sh : les deux blocs -------------
#
# Ces deux blocs vivent dans install.sh, pas dans lib.sh (ce ne sont pas des
# fonctions de décision réutilisables) : on les extrait donc du script réel
# pour les exécuter isolément, plutôt que de les retaper à la main dans le
# test (ce qui pourrait diverger silencieusement du code réellement livré).

def _position_bloc_certificat():
    """Repère (texte, début du "then", début du "else") du if/else qui décide
    de fabriquer ou non le certificat. Ancré sur `if certificat_present`, car
    `\\nelse\\n` seul correspondrait au premier "else" du fichier (celui du
    bloc venv, plus haut) et non à celui qu'on veut extraire."""
    texte = INSTALL.read_text()
    debut_if = texte.index('if certificat_present "$CERT" "$CLE"; then')
    debut_then = texte.index("\n", debut_if) + 1
    debut_else = texte.index("\nelse\n", debut_then)
    return texte, debut_then, debut_else


def _bloc_empreinte_si_deja_present():
    """Le corps du "then" : certificat déjà en place, on affiche l'empreinte."""
    texte, debut_then, debut_else = _position_bloc_certificat()
    return texte[debut_then:debut_else]


def _bloc_fabrication_si_absent():
    """Le corps du "else" (sans le "fi" final, qui referme le "if" d'appel) :
    fabrication du certificat, y compris la gestion de l'échec d'openssl."""
    texte, _, debut_else = _position_bloc_certificat()
    debut = debut_else + len("\nelse\n")
    marqueur_fin = 'info "certificat créé"'
    fin = texte.index(marqueur_fin, debut) + len(marqueur_fin)
    return texte[debut:fin]


def test_empreinte_tolere_une_apostrophe_dans_les_chemins(tmp_path):
    """Avant correction : `$racine` et `$CERT` étaient injectés tels quels
    dans une chaîne Python délimitée par des apostrophes (`'$CERT'`) passée à
    `python -c "..."`. Une apostrophe dans l'un des deux chemins cassait la
    syntaxe Python. Après correction : les valeurs passent par sys.argv (le
    heredoc est quoté, `<<'PY'`), donc leur contenu n'a plus d'importance."""
    dossier = tmp_path / "dossier d'un usager"
    dossier.mkdir()
    cert = dossier / "cert.pem"
    cle = dossier / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-days", "1", "-subj", "/CN=test", "-keyout", str(cle), "-out", str(cert)],
        check=True, capture_output=True,
    )
    # Le dépôt lui-même est atteint par un chemin contenant une apostrophe :
    # un lien symbolique, pour ne pas dépendre d'un vrai dépôt à ce nom.
    lien_racine = tmp_path / "d'un lien vers le dépôt"
    lien_racine.symlink_to(DEPOT)

    script = f'''
set -euo pipefail
info() {{ printf '%s\\n' "$*"; }}
PYTHON=python3
racine="{lien_racine}"
CERT="{cert}"
{_bloc_empreinte_si_deja_present()}
printf '%s' "$empreinte"
'''
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"

    from phototheque import tls
    assert r.stdout.strip().splitlines()[-1] == tls.empreinte_certificat(cert)


def test_echec_openssl_n_est_plus_avale_silencieusement(tmp_path):
    """Avant correction : `openssl ... 2>/dev/null` sans vérification de code
    de sortie. Sous `set -e`, un échec d'openssl arrêtait le script SANS
    AUCUN MESSAGE (stderr jeté à /dev/null). Après correction : la sortie
    d'erreur est capturée puis affichée, et `echec` est appelé explicitement
    avec une piste de dépannage."""
    faux_bin = tmp_path / "bin"
    faux_bin.mkdir()
    faux_openssl = faux_bin / "openssl"
    faux_openssl.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'erreur simulee : impossible d ecrire la cle' >&2\n"
        "exit 1\n"
    )
    faux_openssl.chmod(0o755)

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    cle = config_dir / "key.pem"
    cert = config_dir / "cert.pem"

    script = f'''
set -euo pipefail
info() {{ printf '%s\\n' "$*"; }}
echec() {{ printf 'ECHEC : %s\\n' "$*" >&2; exit 1; }}
CONFIG_DIR="{config_dir}"
CLE="{cle}"
CERT="{cert}"
{_bloc_fabrication_si_absent()}
echo NE_DEVRAIT_JAMAIS_S_AFFICHER
'''
    r = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True,
        env={**os.environ, "PATH": f"{faux_bin}:{os.environ['PATH']}"},
    )
    assert r.returncode == 1
    assert "erreur simulee" in r.stdout + r.stderr, \
        "le message d'erreur d'openssl a été avalé (régression du bug corrigé)"
    assert "ECHEC" in r.stderr
    assert "NE_DEVRAIT_JAMAIS_S_AFFICHER" not in r.stdout
    assert not cert.exists()
