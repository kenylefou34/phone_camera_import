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
    j.noter_refus("sess0", "DCIM/Camera/b.heic", "extension non prise en charge")
    j.enregistrer_commit("s1", "sess0", "tel", "Pixel", None, BILAN, None)
    issues = sorted(m["issue"] for m in j.mouvements("s1"))
    assert issues == ["range", "refuse"]
    assert j.synchros()[0]["refuses"] == 1


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
