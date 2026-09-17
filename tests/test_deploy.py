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


# --- mot de passe d'administration : ne jamais régénérer un secret existant --

def test_install_ne_regenere_jamais_un_secret_existant():
    """Régénérer le mot de passe ou le certificat casserait l'existant."""
    script = "\n".join(_lignes_de_code(LIB.parent / "install.sh"))
    # Les deux créations sont gardées par un test d'existence.
    assert "certificat_present" in script
    assert "[ -f \"$ADMIN\" ]" in script or "-f \"$ADMIN\"" in script


def test_un_echec_ne_laisse_pas_de_fichier_admin_vide(tmp_path):
    """Un échec en cours de génération ne doit pas verrouiller l'admin.

    La garde du script n'est qu'un test d'existence : un fichier vide laissé
    en place serait pris pour un mot de passe valide et jamais régénéré,
    fermant l'accès d'administration sans message ni recours évident.
    """
    # Le script doit écrire dans un fichier temporaire puis le déplacer,
    # jamais directement sur sa destination finale.
    script = "\n".join(_lignes_de_code(LIB.parent / "install.sh"))
    assert '> "$ADMIN"' not in script, "écriture directe sur la destination finale"
    assert 'mv "$ADMIN.nouveau" "$ADMIN"' in script


def _bloc_mot_de_passe():
    """Le bloc if/else complet qui décide de générer (ou non) le mot de
    passe d'administration, extrait du script réel — même raison qu'en tête
    de _bloc_fabrication_si_absent : ne pas retaper le code à la main, au
    risque de diverger silencieusement du code réellement livré."""
    texte = INSTALL.read_text()
    debut = texte.index('if [ -f "$ADMIN" ]; then')
    fin = texte.index("\nfi\n", debut) + len("\nfi")
    return texte[debut:fin]


def test_echec_pendant_la_generation_ne_laisse_pas_de_fichier_admin(tmp_path):
    """Version comportementale du test précédent : exécute réellement le
    bloc avec un faux `python` qui échoue seulement lors du second appel
    (celui qui calcule l'empreinte), et vérifie qu'aucun fichier n'apparaît
    à l'emplacement final — pas même vide."""
    faux_bin = tmp_path / "bin"
    faux_bin.mkdir()
    faux_python = faux_bin / "python"
    faux_python.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"-c\" ] && [[ \"$2\" == *secrets.token_urlsafe* ]]; then\n"
        "    echo motdepassefictif\n"
        "    exit 0\n"
        "fi\n"
        "echo 'erreur simulee : generation de l empreinte' >&2\n"
        "exit 1\n"
    )
    faux_python.chmod(0o755)

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    admin = config_dir / "admin"

    script = f'''
set -euo pipefail
etape() {{ :; }}
info() {{ printf '%s\\n' "$*"; }}
CONFIG_DIR="{config_dir}"
ADMIN="{admin}"
PYTHON="{faux_python}"
racine="{DEPOT}"
{_bloc_mot_de_passe()}
'''
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert r.returncode != 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert not admin.exists(), (
        "un fichier admin (même vide) a été laissé à l'emplacement final : "
        "la garde du prochain lancement le prendrait pour un mot de passe "
        "valide et ne le régénérerait jamais"
    )


# --- nom convivial annoncé en mDNS -------------------------------------------

def test_l_annonce_mdns_porte_un_nom_substituable():
    """install.sh doit pouvoir remplacer le nom affiché sur le réseau."""
    annonce = (LIB.parent / "avahi-phototheque.service").read_text()
    assert "NOM_AFFICHE" in annonce
    script = "\n".join(_lignes_de_code(LIB.parent / "install.sh"))
    assert "NOM_AFFICHE" in script


def _bloc_nom_affiche():
    """Le bloc qui décide du nom affiché sur le réseau et l'injecte dans le
    gabarit Avahi, extrait du script réel (même raison que les blocs
    précédents : ne pas retaper le code à la main, au risque de diverger
    silencieusement du code réellement livré)."""
    texte = INSTALL.read_text()
    debut = texte.index('NOM_AFFICHE="phototheque sur %h"')
    marqueur_fin = 'info "annoncé sur le réseau sous : ${NOM_AFFICHE}"'
    fin = texte.index(marqueur_fin, debut) + len(marqueur_fin)
    return texte[debut:fin]


def _executer_bloc_nom_affiche(config_dir, avahi_dest):
    """Exécute le bloc dans un bash isolé. `sudo` est neutralisé (le bloc
    écrit normalement dans un fichier système via `sudo tee`) ; le gabarit
    utilisé est le vrai fichier du dépôt, comme en production."""
    script = f'''
set -euo pipefail
info() {{ printf '%s\\n' "$*"; }}
sudo() {{ "$@"; }}
CONFIG_DIR="{config_dir}"
SERVICE="phototheque"
AVAHI="{avahi_dest}"
PYTHON=python3
{_bloc_nom_affiche()}
'''
    return subprocess.run(["bash", "-c", script], cwd=DEPOT,
                           capture_output=True, text=True)


def test_annonce_par_defaut_inchangee_sans_fichier_nom(tmp_path):
    """Sans ~/.config/phototheque/nom, l'annonce doit rester exactement celle
    d'avant cette tâche : pas de régression sur le comportement par défaut."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    avahi = tmp_path / "avahi-phototheque.service"
    r = _executer_bloc_nom_affiche(config_dir, avahi)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    contenu = avahi.read_text()
    assert '<name replace-wildcards="yes">phototheque sur %h</name>' in contenu


def test_nom_choisi_remplace_le_nom_par_defaut(tmp_path):
    """Un fichier ~/.config/phototheque/nom présent doit remplacer le nom."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "nom").write_text("Photothèque du salon\n")
    avahi = tmp_path / "avahi-phototheque.service"
    r = _executer_bloc_nom_affiche(config_dir, avahi)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    contenu = avahi.read_text()
    assert '<name replace-wildcards="yes">Photothèque du salon</name>' in contenu


def test_nom_avec_caracteres_speciaux_xml_reste_une_annonce_valide(tmp_path):
    """Un nom contenant &, < ou > casserait le XML s'il était injecté tel
    quel — Avahi refuserait alors de charger le fichier, et l'annonce réseau
    disparaîtrait sans aucun message. Le fichier produit doit rester un XML
    valide, et le nom, une fois décodé, doit correspondre exactement à ce
    que l'usager a tapé (pas de troncature au premier caractère spécial)."""
    import xml.etree.ElementTree as ET

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    nom = "Salon & Cuisine <chez les Dupont>"
    (config_dir / "nom").write_text(nom + "\n")
    avahi = tmp_path / "avahi-phototheque.service"
    r = _executer_bloc_nom_affiche(config_dir, avahi)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"

    arbre = ET.parse(avahi)  # lève une exception si le XML est invalide
    assert arbre.getroot().find("name").text == nom


def test_nom_avec_caracteres_speciaux_pour_sed_ne_casse_pas_la_substitution(tmp_path):
    """Le nom peut contenir des caractères qui ont un sens particulier pour
    `sed` (`/` le délimiteur usuel, `&` la référence arrière, `\\`
    l'échappement) : la méthode de substitution retenue doit les ignorer et
    les transmettre tels quels."""
    import xml.etree.ElementTree as ET

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    nom = "Salon/Cuisine \\1 & Cie"
    (config_dir / "nom").write_text(nom + "\n")
    avahi = tmp_path / "avahi-phototheque.service"
    r = _executer_bloc_nom_affiche(config_dir, avahi)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"

    arbre = ET.parse(avahi)
    assert arbre.getroot().find("name").text == nom


def test_un_fichier_nom_vide_retombe_sur_le_defaut(tmp_path):
    """Fichier vide = « je n'ai rien choisi », pas « annonce un nom vide ».

    Un nom vide casserait la découverte réseau sans aucun message d'erreur :
    fichier XML potentiellement refusé par Avahi, ou service annoncé sans
    nom — dans les deux cas le téléphone ne trouve plus rien, en silence.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "nom").write_text("")
    avahi = tmp_path / "avahi-phototheque.service"
    r = _executer_bloc_nom_affiche(config_dir, avahi)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    contenu = avahi.read_text()
    assert '<name replace-wildcards="yes">phototheque sur %h</name>' in contenu


def test_un_fichier_nom_avec_seulement_des_espaces_retombe_sur_le_defaut(tmp_path):
    """Même chose pour un fichier ne contenant que des blancs (espaces,
    tabulation, ligne vide) : ce n'est pas davantage un nom choisi."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "nom").write_text("   \t  \n")
    avahi = tmp_path / "avahi-phototheque.service"
    r = _executer_bloc_nom_affiche(config_dir, avahi)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    contenu = avahi.read_text()
    assert '<name replace-wildcards="yes">phototheque sur %h</name>' in contenu


# --- test de fumée de l'étape 9 : les codes attendus doivent être les vrais ---

def _codes_attendus_par_install():
    """Les couples (chemin, code attendu) du test de fumée de install.sh.

    Extraits du script réel plutôt que recopiés : c'est tout l'intérêt du
    test, qui compare ce que le script attend à ce que le service renvoie.
    """
    import re
    texte = INSTALL.read_text()
    debut = texte.index("for chemin, attendu in (")
    ligne = texte[debut:texte.index("\n", debut)]
    return [(chemin, int(code))
            for chemin, code in re.findall(r'\("([^"]+)", *(\d+)\)', ligne)]


def _client_comme_en_production(tmp_path, monkeypatch):
    """Un client de test sur un service installé : mot de passe admin en place.

    C'est la situation du test de fumée : le service vient d'être installé,
    personne ne s'authentifie, et on regarde ce qu'il répond.
    """
    import base64  # noqa: F401  (l'en-tête n'est pas utilisé : on n'authentifie pas)
    import importlib
    from fastapi.testclient import TestClient
    from phototheque import adminauth
    fichier = tmp_path / "admin"
    fichier.write_text(adminauth.empreinte("secret-admin", iterations=1000))
    monkeypatch.setenv("ADMIN_FILE", str(fichier))
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path))
    monkeypatch.setenv("CATALOG_DB", str(tmp_path / "cat.db"))
    monkeypatch.setenv("INCOMING_DIR", str(tmp_path / "incoming"))
    monkeypatch.setenv("DEVICES_DB", str(tmp_path / "dev.db"))
    import phototheque.config as c; importlib.reload(c)
    import phototheque.app as a; importlib.reload(a)
    return TestClient(a.app)


def test_le_test_de_fumee_attend_les_codes_reellement_renvoyes(tmp_path, monkeypatch):
    """Le trou par lequel le défaut est passé : le test de fumée a été écrit
    quand `/` et `/pair` étaient ouverts, puis ces adresses sont passées
    derrière le mot de passe admin (issue #10) sans que le script soit repris.
    Résultat : l'installation se terminait toujours en ÉCHEC alors que tout
    était correctement installé. Ce test verrouille l'accord entre les codes
    attendus par install.sh et ceux que le service renvoie vraiment."""
    attendus = _codes_attendus_par_install()
    assert attendus, "bloc de vérification introuvable dans install.sh"
    client = _client_comme_en_production(tmp_path, monkeypatch)
    for chemin, code_attendu in attendus:
        reel = client.get(chemin).status_code
        assert reel == code_attendu, (
            f"install.sh attend {code_attendu} sur {chemin}, "
            f"le service répond {reel} : l'installation se terminerait en ÉCHEC"
        )
