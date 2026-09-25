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

    Importer phototheque.app créait la base (DeviceStore était instancié au
    chargement du module) : un simple test d'existence concluait à tort que la
    reprise avait déjà eu lieu. L'ouverture est devenue paresseuse, mais une
    base vide traînante ne doit toujours pas bloquer la reprise.
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
    # L'écriture doit passer par un fichier temporaire puis un déplacement,
    # jamais directement sur la destination finale. Depuis l'extraction de
    # ecrire_empreinte_admin (partagée avec identifiants.sh), la propriété se
    # vérifie dans lib.sh — et install.sh ne doit plus écrire lui-même.
    fonction = "\n".join(_lignes_de_code(LIB))
    assert '> "$destination"' not in fonction, "écriture directe sur la destination finale"
    assert 'mv "$destination.nouveau" "$destination"' in fonction

    install = "\n".join(_lignes_de_code(LIB.parent / "install.sh"))
    assert '> "$ADMIN"' not in install, "install.sh écrit encore le fichier lui-même"


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

    # Le bloc appelle maintenant ecrire_empreinte_admin : il faut lib.sh.
    script = f'''
set -euo pipefail
source "{LIB}"
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


# --- écriture du mot de passe d'administration (deploy/lib.sh) ----------------
#
# Le mot de passe est écrit à deux endroits : par install.sh à la première
# installation (tirage au hasard) et par identifiants.sh quand le mainteneur en
# choisit un. Les précautions d'écriture — umask, fichier temporaire, 0600 —
# sont donc dans UNE fonction partagée, sous peine de voir les deux copies
# diverger au premier correctif appliqué d'un seul côté.


def appeler_avec_entree(entree, fonction, *arguments):
    """Comme appeler(), mais fournit `entree` sur l'entrée standard.

    Le mot de passe ne transite que par là : jamais par un argument, qui
    serait visible de tout utilisateur de la machine via `ps`.
    """
    script = f'set -euo pipefail; source "{LIB}"; {fonction} ' + " ".join(
        f'"{a}"' for a in arguments
    )
    r = subprocess.run(["bash", "-c", script], input=entree,
                       capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def test_ecrire_empreinte_admin_produit_une_empreinte_verifiable(tmp_path):
    """L'empreinte écrite doit être acceptée par le serveur pour ce mot de passe.

    C'est la seule propriété qui compte vraiment : un fichier bien écrit mais
    que `adminauth.verifier()` rejette fermerait l'administration en silence.
    """
    admin = tmp_path / "admin"
    code, _, err = appeler_avec_entree(
        "mon mot de passe", "ecrire_empreinte_admin", admin, "python3", DEPOT)
    assert code == 0, err

    import sys
    sys.path.insert(0, str(DEPOT))
    from phototheque import adminauth
    assert adminauth.verifier("mon mot de passe", admin.read_text().strip())


def test_ecrire_empreinte_admin_pose_le_fichier_en_0600(tmp_path):
    """Un fichier d'identifiants lisible par les autres comptes n'en est plus un."""
    admin = tmp_path / "admin"
    code, _, err = appeler_avec_entree("secret", "ecrire_empreinte_admin",
                                       admin, "python3", DEPOT)
    assert code == 0, err
    assert oct(admin.stat().st_mode & 0o777) == "0o600"


def test_ecrire_empreinte_admin_remplace_un_mot_de_passe_existant(tmp_path):
    """Changer de mot de passe, c'est écraser l'ancien — pas le conserver.

    C'est la différence avec install.sh, qui refuse de régénérer un secret
    déjà en place. La garde est chez l'appelant, pas dans cette fonction.
    """
    admin = tmp_path / "admin"
    appeler_avec_entree("ancien", "ecrire_empreinte_admin", admin, "python3", DEPOT)
    appeler_avec_entree("nouveau", "ecrire_empreinte_admin", admin, "python3", DEPOT)

    import sys
    sys.path.insert(0, str(DEPOT))
    from phototheque import adminauth
    enregistre = admin.read_text().strip()
    assert adminauth.verifier("nouveau", enregistre)
    assert not adminauth.verifier("ancien", enregistre)


def test_un_echec_d_ecriture_laisse_intact_l_ancien_mot_de_passe(tmp_path):
    """Un échec en cours de route ne doit jamais verrouiller le mainteneur dehors.

    Cas propre à identifiants.sh : il écrase un fichier existant. Si l'écriture
    échouait en détruisant l'ancien mot de passe sans écrire le nouveau,
    l'administration deviendrait inaccessible — sans message, puisque
    verifier() refuse proprement un fichier illisible.
    """
    admin = tmp_path / "admin"
    appeler_avec_entree("ancien", "ecrire_empreinte_admin", admin, "python3", DEPOT)
    avant = admin.read_text()

    faux_python = tmp_path / "python-qui-echoue"
    faux_python.write_text("#!/usr/bin/env bash\necho 'erreur simulee' >&2\nexit 1\n")
    faux_python.chmod(0o755)

    code, _, _ = appeler_avec_entree("nouveau", "ecrire_empreinte_admin",
                                     admin, faux_python, DEPOT)
    assert code != 0, "l'échec de Python doit faire échouer la fonction"
    assert admin.read_text() == avant, "l'ancien mot de passe a été détruit"


def test_ecrire_empreinte_admin_accepte_les_caracteres_qui_piegent_le_shell(tmp_path):
    """Espaces, apostrophes, guillemets, accents, dollar : tous doivent passer.

    C'est précisément là que le shell trahit. Un mot de passe déformé en
    chemin serait invisible : l'écriture réussirait, et seule la connexion
    suivante échouerait, sans que rien n'indique pourquoi.
    """
    complique = "un 'mot' \"de\" passe $PATH `date` \\ àéîôü"
    admin = tmp_path / "admin"
    code, _, err = appeler_avec_entree(complique, "ecrire_empreinte_admin",
                                       admin, "python3", DEPOT)
    assert code == 0, err

    import sys
    sys.path.insert(0, str(DEPOT))
    from phototheque import adminauth
    assert adminauth.verifier(complique, admin.read_text().strip())


# --- deploy/identifiants.sh : choisir son mot de passe --------------------------
#
# install.sh en tire un au hasard à la première installation. Ce script-ci est
# le seul moyen d'en CHOISIR un, et le seul moyen d'en changer sans réinstaller.

IDENTIFIANTS = LIB.parent / "identifiants.sh"


def lancer_identifiants(tmp_path, saisies, python="python3", identifiant=""):
    """Joue le script avec un dossier de configuration jetable.

    `saisies` est la liste des lignes tapées au clavier APRÈS l'identifiant
    (mot de passe, puis confirmation) ; `identifiant` est la première ligne,
    vide par défaut pour conserver l'existant. Le script lit sur l'entrée
    standard, ce qui le rend testable sans pseudo-terminal.
    """
    saisies = [identifiant] + list(saisies)
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    r = subprocess.run(
        ["bash", str(IDENTIFIANTS)],
        input="".join(ligne + "\n" for ligne in saisies),
        capture_output=True, text=True,
        env={**os.environ, "CONFIG_DIR": str(config), "PYTHON": python,
             "RACINE": str(DEPOT)},
    )
    return r, config / "admin"


def test_identifiants_refuse_un_mot_de_passe_vide(tmp_path):
    """Un mot de passe vide fermerait l'administration sans le dire."""
    r, admin = lancer_identifiants(tmp_path, ["", ""])
    # Un refus DÉLIBÉRÉ, pas un script absent ou planté : 127 (introuvable) et
    # 2 (erreur de syntaxe) passeraient un simple « != 0 » sans rien prouver.
    assert r.returncode == 1, f"code {r.returncode} : {r.stderr!r}"
    assert "vide" in (r.stdout + r.stderr).lower(), "le refus n'est pas expliqué"
    assert not admin.exists(), "un mot de passe vide a été enregistré"


def test_identifiants_refuse_deux_saisies_differentes(tmp_path):
    """La confirmation existe pour attraper la faute de frappe.

    Sans elle, une coquille dans un mot de passe qu'on ne voit pas s'affiche
    verrouille l'administration, et le mainteneur ne l'apprend qu'à la
    connexion suivante — sans savoir ce qu'il a tapé.
    """
    r, admin = lancer_identifiants(tmp_path, ["premier-essai", "second-essai"])
    assert r.returncode == 1, f"code {r.returncode} : {r.stderr!r}"
    sortie = (r.stdout + r.stderr).lower()
    assert "identique" in sortie or "diffèrent" in sortie or "different" in sortie, (
        f"le refus n'est pas expliqué : {sortie!r}")
    assert not admin.exists(), "un mot de passe non confirmé a été enregistré"


def test_identifiants_enregistre_le_mot_de_passe_choisi(tmp_path):
    """Le cas nominal : ce qui est tapé devient le mot de passe du serveur."""
    r, admin = lancer_identifiants(tmp_path, ["archibald-42-lapin", "archibald-42-lapin"])
    assert r.returncode == 0, r.stderr

    import sys
    sys.path.insert(0, str(DEPOT))
    from phototheque import adminauth
    assert adminauth.verifier("archibald-42-lapin", admin.read_text().strip())


def test_identifiants_avertit_sur_un_mot_de_passe_court_sans_le_refuser(tmp_path):
    """Court = averti, pas interdit.

    Rien ne limite encore les essais côté serveur (issue #19) : la robustesse
    du mot de passe est donc la seule barrière, et le mainteneur doit le
    savoir. Mais c'est son réseau et son arbitrage — refuser son choix serait
    présomptueux.
    """
    r, admin = lancer_identifiants(tmp_path, ["court", "court"])
    assert r.returncode == 0, r.stderr
    assert admin.exists(), "le mot de passe court aurait dû être accepté"
    sortie = (r.stdout + r.stderr).lower()
    assert "court" in sortie or "faible" in sortie, (
        f"aucun avertissement sur la longueur : {r.stdout!r} {r.stderr!r}")


def test_identifiants_refuse_de_tourner_sans_python_utilisable(tmp_path):
    """Venv absent : le dire franchement plutôt que d'échouer en cours d'écriture."""
    r, admin = lancer_identifiants(tmp_path, ["un-mot-de-passe-correct"] * 2,
                                 python=str(tmp_path / "python-inexistant"))
    assert r.returncode == 1, f"code {r.returncode} : {r.stderr!r}"
    assert not admin.exists()
    assert "python" in (r.stdout + r.stderr).lower()


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


def test_le_test_de_fumee_verifie_aussi_admin():
    """Régression (issue #31, fix round 1) : `/admin` est devenue
    l'administration (`/` sert désormais la galerie). Le test précédent
    verrouille l'ACCORD entre ce que install.sh vérifie et ce que le service
    renvoie, mais ne remarquerait pas qu'une adresse a été oubliée de la
    liste — seulement qu'une adresse présente répond mal. Ce test-ci verrouille
    la PRÉSENCE de `/admin` dans la liste elle-même : sans lui, retirer
    `/admin` du test de fumée de install.sh passerait inaperçu, et une
    administration restée ouverte par erreur après un renommage futur ne
    serait plus détectée à l'installation."""
    attendus = dict(_codes_attendus_par_install())
    assert attendus.get("/admin") == 401


def test_identifiants_enregistre_l_identifiant_choisi(tmp_path):
    """« admin » est le premier nom que tente tout balayage automatique."""
    r, admin = lancer_identifiants(tmp_path, ["un-mot-de-passe-solide"] * 2,
                                 identifiant="ken")
    assert r.returncode == 0, r.stderr
    assert (admin.parent / "utilisateur").read_text().strip() == "ken"


def test_identifiants_vide_conserve_l_identifiant_actuel(tmp_path):
    """Ne rien taper garde l'existant : on vient peut-être seulement changer
    le mot de passe, et écraser l'identifiant au passage verrouillerait
    dehors quelqu'un qui n'a rien demandé."""
    lancer_identifiants(tmp_path, ["premier-mot-de-passe"] * 2, identifiant="ken")
    r, admin = lancer_identifiants(tmp_path, ["second-mot-de-passe"] * 2, identifiant="")
    assert r.returncode == 0, r.stderr
    assert (admin.parent / "utilisateur").read_text().strip() == "ken"


def test_identifiants_affiche_l_identifiant_actuel(tmp_path):
    """Sans cet affichage, un identifiant oublié n'est récupérable que par SSH.

    Ce n'est pas un secret — il n'est pas haché, contrairement au mot de
    passe — donc rien n'interdit de le montrer à qui a déjà le droit de
    lancer ce script.
    """
    lancer_identifiants(tmp_path, ["un-mot-de-passe-solide"] * 2, identifiant="ken")
    r, _ = lancer_identifiants(tmp_path, ["un-mot-de-passe-solide"] * 2, identifiant="")
    assert "ken" in r.stdout + r.stderr, "l'identifiant actuel n'est pas affiché"


def test_identifiants_refuse_un_identifiant_contenant_deux_points(tmp_path):
    """Un « : » rendrait l'identifiant intapable, sans que rien ne l'explique.

    L'authentification HTTP Basic transmet « utilisateur:mot de passe » et le
    serveur découpe sur le PREMIER deux-points : un nom qui en contient un ne
    pourrait jamais être reconnu. Mieux vaut refuser tout de suite que livrer
    une administration dont plus personne n'a la clé.
    """
    r, admin = lancer_identifiants(tmp_path, ["un-mot-de-passe-solide"] * 2,
                                 identifiant="ken:izq")
    assert r.returncode == 1, f"code {r.returncode} : {r.stderr!r}"
    assert not (admin.parent / "utilisateur").exists()
    assert not admin.exists(), "le mot de passe a été changé malgré le refus"


def test_identifiants_affiche_fidelement_un_nom_contenant_un_espace(tmp_path):
    """L'identifiant affiché doit être exactement celui que lit le serveur.

    Le serveur ne rogne que les extrémités (adminauth.utilisateur fait un
    .strip()). Un script qui supprimerait AUSSI les espaces intérieurs
    afficherait « kenizq » là où il faut taper « ken izq » — et le mainteneur
    chercherait longtemps pourquoi son identifiant est refusé.
    """
    r, admin = lancer_identifiants(tmp_path, ["un-mot-de-passe-solide"] * 2,
                                   identifiant="ken izq")
    assert r.returncode == 0, r.stderr
    assert (admin.parent / "utilisateur").read_text().strip() == "ken izq"

    # Relancé : il doit réafficher le nom intact.
    r2, _ = lancer_identifiants(tmp_path, ["un-mot-de-passe-solide"] * 2, identifiant="")
    assert "ken izq" in r2.stdout + r2.stderr, (
        f"nom deforme a l'affichage : {r2.stdout!r}")


# --------------------------------------------- version lue dans le gradle

def test_version_depuis_gradle_lit_le_nom_et_le_code(tmp_path):
    gradle = tmp_path / "build.gradle.kts"
    gradle.write_text('android {\n  defaultConfig {\n'
                      '    versionCode = 7\n    versionName = "1.2.3"\n  }\n}\n')
    code, sortie = appeler("version_depuis_gradle", str(gradle))
    assert code == 0 and sortie == "1.2.3 7"


def test_version_depuis_gradle_sans_fichier_ne_fait_pas_echouer(tmp_path):
    """Le script appelant tourne sous `set -e` : un repli doit rendre 0."""
    code, sortie = appeler("version_depuis_gradle", str(tmp_path / "absent.kts"))
    assert code == 0 and sortie == "inconnue 0"


def test_version_depuis_gradle_sans_version_declaree(tmp_path):
    gradle = tmp_path / "build.gradle.kts"
    gradle.write_text("android {\n  namespace = \"fr.exemple\"\n}\n")
    code, sortie = appeler("version_depuis_gradle", str(gradle))
    assert code == 0 and sortie == "inconnue 0"


def test_version_depuis_gradle_garde_la_premiere_occurrence(tmp_path):
    """Plusieurs modules dans un même fichier : c'est le premier qui compte.

    Et surtout : la fonction ne doit pas utiliser `| head -1`, qui renverrait
    141 sous `set -o pipefail` et ferait avorter le script appelant. Ce test
    échouerait alors sur le code de sortie, pas sur la valeur.
    """
    gradle = tmp_path / "build.gradle.kts"
    gradle.write_text('versionName = "1.0"\nversionCode = 1\n'
                      'versionName = "2.0"\nversionCode = 2\n')
    code, sortie = appeler("version_depuis_gradle", str(gradle))
    assert code == 0 and sortie == "1.0 1"


def test_le_script_d_envoi_est_executable_et_sain():
    envoi = LIB.parent / "envoyer-apk.sh"
    assert envoi.exists() and os.access(envoi, os.X_OK)
    r = subprocess.run(["bash", "-n", str(envoi)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_le_script_d_envoi_refuse_un_argument_inconnu():
    envoi = LIB.parent / "envoyer-apk.sh"
    r = subprocess.run(["bash", str(envoi), "--nimporte-quoi"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "inconnu" in r.stderr


# ------------------------------------------- trouver le NUC sur le reseau

def test_premiere_adresse_prend_l_ipv4(tmp_path):
    code, sortie = appeler("premiere_adresse", "192.168.1.21   nuc.local")
    assert code == 0 and sortie == "192.168.1.21"


def test_premiere_adresse_saute_l_ipv6(tmp_path):
    """getent rend souvent l'IPv6 en premier.

    Une adresse lien-local IPv6 exige un suffixe d'interface que ni ssh ni scp
    ne reçoivent ici : la retenir ferait échouer le transfert avec un message
    incompréhensible.
    """
    code, sortie = appeler(
        "premiere_adresse", "fe80::1   nuc.local\n192.168.1.21   nuc.local")
    assert code == 0 and sortie == "192.168.1.21"


def test_premiere_adresse_sans_resolution_rend_1():
    """Aucune adresse : l'appelant doit pouvoir le distinguer d'une réussite."""
    code, sortie = appeler("premiere_adresse", "")
    assert code == 1 and sortie == ""


def test_premiere_adresse_ipv6_seule_rend_1():
    code, _ = appeler("premiere_adresse", "fe80::1   nuc.local")
    assert code == 1


def test_port_ouvert_faux_sur_un_port_ferme():
    """Le port 1 n'écoute nulle part."""
    code, _ = appeler("port_ouvert", "127.0.0.1", "1", "1")
    assert code != 0


def test_port_ouvert_vrai_sur_un_port_qui_ecoute():
    import socket
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)
    port = serveur.getsockname()[1]
    try:
        code, _ = appeler("port_ouvert", "127.0.0.1", str(port), "2")
        assert code == 0
    finally:
        serveur.close()


def test_adresse_nuc_retient_ce_que_le_mdns_resout_si_ca_repond():
    """`127.0.0.1` tient lieu de nom mDNS : il « résout » et le port répond.

    Pas `localhost` : sur cette machine il ne résout qu'en `::1`, et
    `premiere_adresse` écarte volontairement l'IPv6 — une adresse lien-local
    exigerait un suffixe d'interface que ssh ne reçoit pas ici.
    """
    import socket
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)
    port = serveur.getsockname()[1]
    try:
        code, sortie = appeler("adresse_nuc", "127.0.0.1", "", str(port))
        assert code == 0 and sortie.splitlines()[-1] == "127.0.0.1"
    finally:
        serveur.close()


def test_adresse_nuc_bascule_sur_le_repli_quand_le_nom_ne_repond_pas():
    """Le nom résout mais rien n'écoute : le repli doit prendre le relais.

    C'est le cas du 23/09 : `.21` répondait au ping et rien n'y écoutait,
    l'adresse ayant été reprise par un autre appareil.
    """
    import socket
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)
    port = serveur.getsockname()[1]
    try:
        # « nom-qui-nexiste-pas » ne résout pas -> repli sur 127.0.0.1
        code, sortie = appeler(
            "adresse_nuc", "nom-qui-nexiste-pas.invalid", "127.0.0.1", str(port))
        assert code == 0 and sortie.splitlines()[-1] == "127.0.0.1"
    finally:
        serveur.close()


def test_adresse_nuc_echoue_quand_rien_ne_repond():
    """Ni le nom ni le repli : il faut rendre 1, pas une adresse au hasard.

    Sans ça, le script enverrait l'APK dans le vide et signalerait une
    réussite.
    """
    code, sortie = appeler(
        "adresse_nuc", "nom-qui-nexiste-pas.invalid", "127.0.0.1", "1")
    assert code == 1
    assert "127.0.0.1" not in sortie.splitlines()[-1:] or sortie == ""


def test_le_script_d_envoi_reste_sain():
    envoi = LIB.parent / "envoyer-apk.sh"
    r = subprocess.run(["bash", "-n", str(envoi)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_adresse_nuc_SONDE_ce_que_le_mdns_resout_avant_de_le_retenir():
    """Le nom résout, mais rien n'écoute à cette adresse : il faut replier.

    C'est le cas vécu le 23/09 : `IZQUIERDO-NUC.local` résolvait parfaitement
    en `192.168.1.21`, et le port ne répondait pas — le lien radio battait.
    Faire confiance à la résolution seule enverrait l'APK dans le vide en
    annonçant une réussite.

    Ce test existe parce que la mutation « retirer la sonde » ne faisait
    tomber AUCUN test : les autres passent par un nom qui ne résout pas du
    tout, et n'exercent donc jamais cette branche.
    """
    import socket
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen(1)
    port = serveur.getsockname()[1]
    try:
        # 127.0.0.2 « resout » (adresse litterale) mais rien n'y ecoute ;
        # 127.0.0.1 est le repli, et lui repond.
        code, sortie = appeler(
            "adresse_nuc", "127.0.0.2", "127.0.0.1", str(port))
        assert code == 0
        assert sortie.splitlines()[-1] == "127.0.0.1"
    finally:
        serveur.close()


def test_adresse_avahi_prend_le_dernier_champ():
    """`avahi-resolve` met l'adresse en DERNIER, `getent` en premier.

    Un analyseur unique se tromperait sur l'un des deux — d'où deux fonctions.
    """
    code, sortie = appeler("adresse_avahi", "IZQUIERDO-NUC.local\t192.168.1.31")
    assert code == 0 and sortie == "192.168.1.31"


def test_adresse_avahi_saute_l_ipv6():
    """Sans `-4`, avahi rend l'IPv6 en premier ; on ne la retient pas."""
    code, _ = appeler(
        "adresse_avahi", "IZQUIERDO-NUC.local\t2a01:cb1d:8ea0:700:a496:569a:2bfd:2be5")
    assert code == 1


def test_adresse_avahi_sur_une_sortie_vide_rend_1():
    code, _ = appeler("adresse_avahi", "")
    assert code == 1


def test_resoudre_mdns_retombe_sur_getent_quand_avahi_ne_sait_pas():
    """avahi ne résout pas une IP littérale ; getent, si.

    C'est la bretelle de secours : le 23/09 c'est l'inverse qui s'est produit
    — `getent` a échoué dix fois d'affilée pendant qu'`avahi-resolve`
    répondait — mais les deux sens doivent tenir.
    """
    code, sortie = appeler("resoudre_mdns", "127.0.0.1")
    assert code == 0 and sortie == "127.0.0.1"


def test_resoudre_mdns_rend_1_quand_personne_ne_sait():
    code, _ = appeler("resoudre_mdns", "nom-qui-nexiste-pas.invalid")
    assert code == 1


# ------------------------------------ service du recensement (issue #31) ---

def test_l_unite_du_recensement_est_discrete():
    """Le NUC a 2 cœurs : le recensement passe après tout le reste."""
    unite = (LIB.parent / "phototheque-recensement.service").read_text()
    assert "-m phototheque.recensement" in unite
    assert "Nice=19" in unite
    assert "IOSchedulingClass=idle" in unite
    assert "RequiresMountsFor=/media/izquierdo/Famille" in unite


def test_l_unite_du_recensement_laisse_le_temps_de_finir_un_lot():
    """Par défaut systemd tue au bout de 90 s après SIGTERM ; un lot peut
    durer plus (relecture finale #31, I2)."""
    unite = (LIB.parent / "phototheque-recensement.service").read_text()
    assert "\nTimeoutStopSec=300\n" in unite


def test_install_installe_et_demarre_le_recensement():
    script = (LIB.parent / "install.sh").read_text()
    assert "phototheque-recensement.service" in script
    assert "systemctl enable phototheque-recensement.service" in script
    assert "systemctl restart phototheque-recensement.service" in script
