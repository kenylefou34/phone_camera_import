import pytest

from phototheque.journal import Journal

BILAN = {"sorted": 2, "duplicates": 1, "to_triage": 0, "errors": 0,
         "ignores": 0, "octets_ranges": 300}


def test_trois_paquets_font_une_seule_synchro(tmp_path):
    """Spec §8.1 : le regroupement par identifiant de synchro fonctionne."""
    j = Journal(tmp_path / "j.db")
    for n in range(3):
        j.enregistrer_commit("s1", f"sess{n}", "tel", "Pixel", "192.168.1.18", BILAN, None)
    lignes = j.synchros()
    assert len(lignes) == 1
    assert lignes[0]["paquets"] == 3 and lignes[0]["ranges"] == 6
    assert lignes[0]["octets"] == 900 and lignes[0]["etat"] == "terminee"


def test_les_mouvements_sont_rattaches_a_leur_synchro(tmp_path):
    j = Journal(tmp_path / "j.db")
    j.ajouter_mouvement("sess0", {"origine": "DCIM/Camera/a.jpg", "taille": 1,
                                  "empreinte": "e1", "issue": "range",
                                  "destination": "/b/a.jpg", "detail": None})
    j.noter_refus("sess0", "DCIM/Camera/b.webm", "extension non prise en charge")
    j.enregistrer_commit("s1", "sess0", "tel", "Pixel", None, BILAN, None)
    issues = sorted(m["issue"] for m in j.mouvements("s1"))
    assert issues == ["range", "refuse_envoi"]
    assert j.synchros()[0]["refuses"] == 1


def test_un_fichier_ignore_par_le_trieur_n_est_pas_compte_deux_fois(tmp_path):
    """M1 (relecture finale), cas reproduit : un refus à l'envoi + un reliquat
    `.partiel` (processus tué pendant un envoi, issue #21) ignoré par le trieur.

    Le trieur écrit déjà un mouvement `refuse` pour chaque fichier qu'il
    ignore, ET le compte dans `ignores` : compter aussi ces mouvements-là
    donnait `refuses == 3` pour deux fichiers. Seuls les refus À L'ENVOI
    (`refuse_envoi`, jamais vus par le trieur) s'ajoutent à `ignores`.
    """
    j = Journal(tmp_path / "j.db")
    j.noter_refus("sess0", "Movies/film.webm", "extension non prise en charge")
    j.ajouter_mouvement("sess0", {"origine": "DCIM/IMG_1.jpg.partiel", "taille": 4,
                                  "empreinte": None, "issue": "refuse",
                                  "destination": None, "detail": "extension non gérée"})
    j.enregistrer_commit("s1", "sess0", "tel", None, None,
                         dict(BILAN, sorted=0, duplicates=0, ignores=1), None)
    assert j.synchro("s1")["refuses"] == 2


def test_un_envoi_fait_seulement_d_exclus_compte_ses_fichiers(tmp_path):
    """M1 : un fichier exclu (sous-dossier WhatsApp « Sent »…) a bien été REÇU
    par le serveur. Sans `skipped` dans `envoyes`, une synchro faite
    seulement d'exclus affichait « 0 fichier(s) » en listant N lignes."""
    j = Journal(tmp_path / "j.db")
    j.enregistrer_commit("s1", "sess0", "tel", None, None,
                         {"sorted": 0, "duplicates": 0, "to_triage": 0, "errors": 0,
                          "ignores": 0, "skipped": 3, "octets_ranges": 0}, None)
    assert j.synchro("s1")["envoyes"] == 3


def test_le_label_est_une_copie(tmp_path):
    """Spec §8.5 : supprimer l'appareil ne doit pas effacer son histoire."""
    j = Journal(tmp_path / "j.db")
    j.enregistrer_commit("s1", "sess0", "tel", "Pixel de Ken", None, BILAN, None)
    assert j.synchro("s1")["label"] == "Pixel de Ken"


def test_le_bilan_de_l_application_est_retenu(tmp_path):
    j = Journal(tmp_path / "j.db")
    j.enregistrer_commit("s1", "sess0", "tel", None, None, BILAN,
                         {"envoyes": 3, "refuses": 0, "echecs": 2})
    assert j.synchro("s1")["app_echecs"] == 2


def test_la_recherche_trouve_par_nom_et_par_empreinte(tmp_path):
    j = Journal(tmp_path / "j.db")
    j.ajouter_mouvement("sess0", {"origine": "DCIM/Camera/IMG_1.jpg", "taille": 1,
                                  "empreinte": "abc", "issue": "range",
                                  "destination": "/b/IMG_1.jpg", "detail": None})
    j.enregistrer_commit("s1", "sess0", "tel", None, None, BILAN, None)
    assert len(j.rechercher("IMG_1")) == 1
    assert len(j.rechercher("abc")) == 1
    assert j.rechercher("%") == []      # un joker SQL ne doit pas tout ramener


def test_un_commit_rejoue_ne_recompte_pas(tmp_path):
    """Fix round 1 : une reponse HTTP perdue fait rejouer /sync/commit avec la
    meme session -> le bilan ne doit pas doubler."""
    j = Journal(tmp_path / "j.db")
    j.enregistrer_commit("s1", "sess0", "tel", "Pixel", None, BILAN, None)
    j.enregistrer_commit("s1", "sess0", "tel", "Pixel", None, BILAN, None)  # rejeu
    ligne = j.synchros()[0]
    assert ligne["paquets"] == 1
    assert ligne["ranges"] == 2 and ligne["doublons"] == 1
    assert ligne["octets"] == 300 and ligne["envoyes"] == 3


def test_les_evenements_sont_rendus_du_plus_recent_au_plus_ancien(tmp_path):
    j = Journal(tmp_path / "j.db")
    j.evenement("demarrage")
    j.evenement("appairage", appareil="tel")
    assert [e["type"] for e in j.evenements()] == ["appairage", "demarrage"]


def test_le_journal_retient_les_sessions_retirees(tmp_path):
    """M6 : une session purgée ou abandonnée est retenue, pour qu'un commit
    tardif sur elle soit refusé au lieu de passer pour une session vide."""
    j = Journal(tmp_path / "j.db")
    assert j.session_retiree("a" * 32) is False
    j.retirer_session("a" * 32, "abandon")
    j.retirer_session("a" * 32, "purge")          # deuxième fois : sans erreur
    assert j.session_retiree("a" * 32) is True
    assert j.session_retiree("b" * 32) is False
    # Et ça survit à la réouverture de la base (le service redémarre).
    j.close()
    assert Journal(tmp_path / "j.db").session_retiree("a" * 32) is True


def test_un_commit_qui_casse_au_milieu_ne_laisse_rien_a_moitie_ecrit(tmp_path):
    """M2 (relecture finale) : chaque écriture est une transaction entière.

    Reproduit : une valeur que SQLite ne sait pas stocker (entier de plus de
    64 bits) fait lever la DERNIÈRE requête d'`enregistrer_commit`. Sans
    transaction, les lignes `commits` et `synchros` déjà insérées restaient
    en attente dans la connexion, et l'écriture SUIVANTE (n'importe laquelle)
    les validait : la session passait pour « déjà appliquée » pour toujours,
    avec une synchro figée à « en cours » et zéro paquet.
    """
    j = Journal(tmp_path / "j.db")
    with pytest.raises(OverflowError):
        j.enregistrer_commit("s1", "sess0", "tel", "Pixel", None, BILAN,
                             {"echecs": 10**30})
    j.evenement("demarrage")          # l'écriture suivante ne doit rien valider d'autre

    assert j.synchros() == []
    # La même session, cette fois correcte, s'enregistre normalement.
    j.enregistrer_commit("s1", "sess0", "tel", "Pixel", None, BILAN, None)
    ligne = j.synchro("s1")
    assert ligne["paquets"] == 1 and ligne["etat"] == "terminee"
