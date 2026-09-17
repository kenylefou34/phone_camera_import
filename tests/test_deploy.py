"""Tests des décisions prises par le script de déploiement (deploy/lib.sh).

Pourquoi tester un script shell : le 17/09/2026, deux décisions de
`deploy/install.sh` se sont trompées en production et ont mis le service en
boucle de redémarrage. Les deux sont maintenant des fonctions isolées, sans
effet de bord, appelables depuis ces tests.
"""

import sqlite3
import subprocess
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "deploy" / "lib.sh"


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
