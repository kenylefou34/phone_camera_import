"""Quarantaine des médias qu'un tri n'a pas su ranger (issue #16).

Le serveur les DÉTRUISAIT : `sessions.cleanup()` supprime le dossier de session
sans regarder le bilan, et un fichier en échec y reste. La garantie « le
téléphone le reproposera » repose entièrement sur un tiers — une application qui
libère la place après envoi, un DCIM vidé à la main, et l'unique copie restante
avait disparu.
"""

from pathlib import Path

from phototheque import quarantaine


def _session_avec(tmp_path: Path, chemin: str, contenu: bytes) -> Path:
    session = tmp_path / "incoming" / ("a" * 32)
    (session / chemin).parent.mkdir(parents=True, exist_ok=True)
    (session / chemin).write_bytes(contenu)
    return session


def test_le_fichier_en_echec_survit_au_nettoyage(tmp_path):
    """Le fichier est DÉPLACÉ hors de la session, donc il survit au rmtree."""
    session = _session_avec(tmp_path, "sous/a.jpg", b"photo-a")
    abri = tmp_path / "incoming" / "_echecs"

    quarantaine.mettre_de_cote(
        session, [{"fichier": "sous/a.jpg", "raison": "disque plein"}], abri)

    assert (abri / "sous" / "a.jpg").read_bytes() == b"photo-a"
    assert not (session / "sous" / "a.jpg").exists()


def test_deux_fichiers_differents_de_meme_chemin_survivent_tous_les_deux(tmp_path):
    """Deux contenus differents au meme chemin : aucun ne doit ecraser l'autre.

    C'est le piège du rangement à plat par chemin relatif. Sans ce contrôle, la
    quarantaine détruirait à son tour — exactement ce qu'elle existe pour
    empêcher.
    """
    abri = tmp_path / "incoming" / "_echecs"
    for contenu in (b"photo-a", b"photo-DIFFERENTE"):
        session = _session_avec(tmp_path, "sous/a.jpg", contenu)
        quarantaine.mettre_de_cote(
            session, [{"fichier": "sous/a.jpg", "raison": "disque plein"}], abri)

    gardes = quarantaine.lister(abri)
    assert len(gardes) == 2, gardes
    assert {(abri / e["fichier"]).read_bytes() for e in gardes} == {
        b"photo-a", b"photo-DIFFERENTE"}


def test_le_meme_fichier_en_echec_deux_fois_n_occupe_qu_une_place(tmp_path):
    """La boucle est bornee : meme contenu au meme chemin = une seule copie.

    Le defaut est repetitif par nature : le fichier echoue, l'horizon n'avance
    pas, le telephone le renvoie, il echoue pareil. Sans cette borne, une video
    de 3 Go en echec ferait 90 Go par mois.
    """
    abri = tmp_path / "incoming" / "_echecs"
    for _ in range(3):
        session = _session_avec(tmp_path, "sous/a.jpg", b"photo-a")
        quarantaine.mettre_de_cote(
            session, [{"fichier": "sous/a.jpg", "raison": "disque plein"}], abri)

    gardes = quarantaine.lister(abri)
    assert len(gardes) == 1, gardes
    assert (abri / gardes[0]["fichier"]).read_bytes() == b"photo-a"


def test_la_raison_de_l_echec_est_conservee(tmp_path):
    """Un fichier mis de côté sans sa raison ne se diagnostique plus après coup."""
    session = _session_avec(tmp_path, "sous/a.jpg", b"photo-a")
    abri = tmp_path / "incoming" / "_echecs"

    quarantaine.mettre_de_cote(
        session, [{"fichier": "sous/a.jpg", "raison": "disque plein"}], abri)
    listing = quarantaine.lister(abri)

    assert len(listing) == 1, listing
    assert listing[0]["fichier"] == "sous/a.jpg"
    assert listing[0]["raison"] == "disque plein"
    assert listing[0]["octets"] == len(b"photo-a")
    assert listing[0]["date"]        # horodatage présent


def test_la_raison_suit_le_fichier_renomme(tmp_path):
    """Quand un homonyme force un suffixe, la raison doit suivre le NOUVEAU nom."""
    abri = tmp_path / "incoming" / "_echecs"
    for contenu, raison in ((b"photo-a", "disque plein"),
                            (b"photo-DIFFERENTE", "fichier illisible")):
        session = _session_avec(tmp_path, "a.jpg", contenu)
        quarantaine.mettre_de_cote(
            session, [{"fichier": "a.jpg", "raison": raison}], abri)

    raisons = {e["fichier"]: e["raison"] for e in quarantaine.lister(abri)}
    assert raisons == {"a.jpg": "disque plein", "a_1.jpg": "fichier illisible"}


def test_lister_un_abri_absent_ne_leve_pas(tmp_path):
    """Cas normal : aucun échec n'a jamais eu lieu, le dossier n'existe pas."""
    assert quarantaine.lister(tmp_path / "jamais-cree") == []


def test_purger_vide_l_abri_et_dit_combien(tmp_path):
    """La purge est MANUELLE : une purge à l'ancienneté réintroduirait le défaut."""
    abri = tmp_path / "incoming" / "_echecs"
    for nom in ("a.jpg", "b.jpg"):
        session = _session_avec(tmp_path, nom, b"contenu " + nom.encode())
        quarantaine.mettre_de_cote(
            session, [{"fichier": nom, "raison": "disque plein"}], abri)

    retires = quarantaine.purger(abri)

    assert retires == 2
    assert quarantaine.lister(abri) == []


def test_purger_un_abri_absent_ne_leve_pas(tmp_path):
    assert quarantaine.purger(tmp_path / "jamais-cree") == 0
