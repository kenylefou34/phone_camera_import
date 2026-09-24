import io
import os
import time
from pathlib import Path

import pytest
from phototheque import sessions


class FluxRefusantLaLectureEntiere(io.RawIOBase):
    """Flux qui lève si on lui demande tout son contenu d'un seul coup.

    C'est l'outil qui permet de VÉRIFIER la propriété de l'issue #21, plutôt
    que de mesurer une consommation mémoire — mesure fragile et dépendante de
    la machine. Ici, la seule façon de faire passer le test est de lire par
    blocs bornés : une lecture intégrale échoue, bruyamment et toujours.
    """

    def __init__(self, contenu: bytes, bloc_max: int):
        self._reste = contenu
        self._bloc_max = bloc_max
        self.plus_gros_bloc_demande = 0

    def read(self, taille=-1):
        if taille is None or taille < 0:
            raise AssertionError(
                "lecture intégrale demandée : tout le fichier passerait en "
                "mémoire, c'est exactement ce que l'issue #21 corrige")
        if taille > self._bloc_max:
            raise AssertionError(
                f"bloc de {taille} octets demandé, au-delà de {self._bloc_max}")
        self.plus_gros_bloc_demande = max(self.plus_gros_bloc_demande, taille)
        morceau, self._reste = self._reste[:taille], self._reste[taille:]
        return morceau

    def readinto(self, tampon):
        morceau = self.read(len(tampon))
        tampon[:len(morceau)] = morceau
        return len(morceau)

    def readable(self):
        return True


def test_save_upload_writes_under_session(tmp_path):
    s = sessions.new_session()
    p = sessions.save_upload(tmp_path, s, "Pictures/WhatsApp/a.jpg", io.BytesIO(b"data"))
    assert p.read_bytes() == b"data"
    assert (tmp_path / s / "Pictures" / "WhatsApp" / "a.jpg") == p


def test_save_upload_rejects_traversal(tmp_path):
    s = sessions.new_session()
    with pytest.raises(ValueError):
        sessions.save_upload(tmp_path, s, "../../etc/passwd", io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        sessions.save_upload(tmp_path, s, "/abs/chemin.jpg", io.BytesIO(b"x"))


def test_cleanup_removes_session(tmp_path):
    s = sessions.new_session()
    sessions.save_upload(tmp_path, s, "a.jpg", io.BytesIO(b"x"))
    sessions.cleanup(tmp_path, s)
    assert not (tmp_path / s).exists()


def test_identifiant_valide_reconnait_ce_que_produit_new_session():
    """La forme attendue : 32 caractères hexadécimaux, rien d'autre."""
    assert sessions.identifiant_valide(sessions.new_session())
    for mauvais in ("", "inexistante", "../..", "/etc", "a" * 31, "A" * 32,
                    sessions.new_session() + "x"):
        assert not sessions.identifiant_valide(mauvais), mauvais


def test_un_identifiant_de_session_hors_norme_ne_sort_pas_du_dossier(tmp_path):
    """L'identifiant de session lui-même doit être contrôlé, pas seulement le
    chemin du fichier : « .. » comme session ferait écrire — puis effacer par
    le nettoyage de fin de synchro — un dossier voisin du dépôt des envois."""
    base = tmp_path / "incoming"
    voisin = tmp_path / "a_ne_pas_toucher"
    voisin.mkdir(parents=True)
    (voisin / "precieux.txt").write_text("à garder")

    with pytest.raises(ValueError):
        sessions.save_upload(base, "../a_ne_pas_toucher", "a.jpg", io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        sessions.cleanup(base, "../a_ne_pas_toucher")

    assert (voisin / "precieux.txt").exists()


# --- issue #21 : ne jamais charger tout le fichier en mémoire ----------------


def test_save_upload_ne_charge_jamais_tout_le_fichier_en_memoire(tmp_path):
    """Le fichier doit être écrit par blocs bornés, quelle que soit sa taille.

    Le NUC a 3,1 Gio de mémoire dont 1,7 disponible, et le projet manipule des
    vidéos de 3,6 Gio (issue #14). Charger le fichier entier faisait tuer le
    service par le noyau, redémarrer, et recommencer sur le même fichier — une
    boucle sans fin dont le symptôme ne désigne pas la cause.
    """
    contenu = b"x" * (3 * 1024 * 1024 + 7)      # 3 Mio et des poussières
    flux = FluxRefusantLaLectureEntiere(contenu, bloc_max=sessions.TAILLE_BLOC)
    s = sessions.new_session()

    cible = sessions.save_upload(tmp_path, s, "video.mp4", flux)

    assert cible.read_bytes() == contenu, "contenu déformé par l'écriture par blocs"
    assert flux.plus_gros_bloc_demande <= sessions.TAILLE_BLOC


def test_un_envoi_interrompu_ne_laisse_pas_de_fichier_a_moitie_ecrit(tmp_path):
    """Une coupure en cours d'envoi ne doit rien laisser à l'emplacement final.

    Un fichier tronqué portant une extension de média serait pris pour un
    média valide par le trieur : il serait rangé dans la bibliothèque, compté
    comme reçu, et l'original sur le téléphone ne serait plus jamais proposé.
    """
    class FluxQuiCasse(FluxRefusantLaLectureEntiere):
        def read(self, taille=-1):
            morceau = super().read(taille)
            if self.plus_gros_bloc_demande and not morceau:
                raise OSError("connexion interrompue")
            return morceau

    s = sessions.new_session()
    flux = FluxQuiCasse(b"y" * 4096, bloc_max=sessions.TAILLE_BLOC)
    with pytest.raises(OSError):
        sessions.save_upload(tmp_path, s, "photo.jpg", flux)

    assert not (tmp_path / s / "photo.jpg").exists(), (
        "un fichier tronqué a été laissé à l'emplacement final")


def test_la_traversee_est_refusee_avant_la_moindre_ecriture(tmp_path):
    """Le contrôle de chemin doit précéder l'ouverture du fichier de sortie.

    Contrôler après aurait déjà créé le dossier — voire le fichier — à
    l'endroit interdit avant de lever l'erreur.
    """
    s = sessions.new_session()
    flux = FluxRefusantLaLectureEntiere(b"x" * 100, bloc_max=sessions.TAILLE_BLOC)
    with pytest.raises(ValueError):
        sessions.save_upload(tmp_path, s, "../dehors.jpg", flux)

    assert flux.plus_gros_bloc_demande == 0, "le flux a été lu malgré le refus"
    assert not (tmp_path / "dehors.jpg").exists()


# --- issue #30 : purge des sessions abandonnées et POST /sync/abandon -------


def _vieillir(chemin, secondes):
    """Recule la date de modification de `chemin` et de tout son contenu."""
    t = time.time() - secondes
    for p in [chemin, *chemin.rglob("*")]:
        os.utime(p, (t, t))


def test_une_session_de_25_heures_est_purgee_une_recente_survit(tmp_path):
    """Spec §8.6."""
    vieille = tmp_path / ("a" * 32); (vieille / "DCIM").mkdir(parents=True)
    (vieille / "DCIM" / "x.jpg").write_bytes(b"123")
    recente = tmp_path / ("b" * 32); recente.mkdir(); (recente / "y.jpg").write_bytes(b"1")
    _vieillir(vieille, 25 * 3600); _vieillir(recente, 60)
    emportees = sessions.purger_abandonnees(tmp_path)
    assert [e["session"] for e in emportees] == ["a" * 32]
    assert emportees[0]["fichiers"] == 1 and emportees[0]["octets"] == 3
    assert not vieille.exists() and recente.exists()


def test_la_quarantaine_n_est_jamais_purgee(tmp_path):
    """Point d'attention 1 : purger _echecs réintroduirait l'issue #16."""
    abri = tmp_path / "_echecs" / "DCIM"; abri.mkdir(parents=True)
    (abri / "z.jpg").write_bytes(b"1")
    _vieillir(tmp_path / "_echecs", 400 * 24 * 3600)
    assert sessions.purger_abandonnees(tmp_path) == []
    assert (abri / "z.jpg").exists()


def test_une_reception_en_cours_dans_un_sous_dossier_protege_la_session(tmp_path):
    """Point d'attention 2 : la date du dossier de session ne bouge pas quand
    un fichier arrive dans un sous-dossier — seule celle du sous-dossier."""
    s = tmp_path / ("c" * 32); (s / "DCIM" / "Camera").mkdir(parents=True)
    (s / "DCIM" / "Camera" / "v.mp4.partiel").write_bytes(b"1")
    _vieillir(s, 30 * 3600)
    os.utime(s / "DCIM" / "Camera" / "v.mp4.partiel")     # écrit à l'instant
    assert sessions.purger_abandonnees(tmp_path) == []


def test_abandonner_refuse_un_identifiant_hors_norme(tmp_path):
    """Spec §8.7 : `..` ne doit rien supprimer du tout."""
    voisin = tmp_path / "voisin"; voisin.mkdir(); (voisin / "garde.jpg").write_bytes(b"1")
    base = tmp_path / "incoming"; base.mkdir()
    with pytest.raises(ValueError):
        sessions.abandonner(base, "../voisin")
    assert (voisin / "garde.jpg").exists()


def test_abandonner_rend_ce_qui_a_ete_supprime(tmp_path):
    s = tmp_path / ("d" * 32); s.mkdir(); (s / "a.jpg").write_bytes(b"12345")
    assert sessions.abandonner(tmp_path, "d" * 32) == {"supprimes": 1, "octets": 5}
    assert not s.exists()


# --- relecture round 1 : isolation par session, symlink, filtre réel --------


def test_une_session_qui_leve_n_empeche_pas_les_autres_d_etre_purgees(tmp_path, monkeypatch):
    """Important (relecture round 1) : une session dont le traitement casse

    (`stat()` impossible, `rmtree` qui échoue sur le disque externe NTFS...)
    ne doit ni faire perdre les sessions DÉJÀ purgées dans la même passe
    (la liste n'était rendue qu'à la toute fin, une levée en cours de route
    la perdait entièrement), ni empêcher les sessions SUIVANTES d'être
    purgées à leur tour — et la fonction elle-même ne doit jamais lever.
    """
    a_dir = tmp_path / ("a" * 32); a_dir.mkdir(); (a_dir / "x.jpg").write_bytes(b"1")
    b_dir = tmp_path / ("b" * 32); b_dir.mkdir(); (b_dir / "y.jpg").write_bytes(b"1")
    c_dir = tmp_path / ("c" * 32); c_dir.mkdir(); (c_dir / "z.jpg").write_bytes(b"1")
    for d in (a_dir, b_dir, c_dir):
        _vieillir(d, 25 * 3600)

    fichier_qui_casse = b_dir / "y.jpg"
    stat_reel = Path.stat

    def stat_qui_casse(self, *args, **kwargs):
        if self == fichier_qui_casse:
            raise PermissionError("panne simulee")
        return stat_reel(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat_qui_casse)

    emportees = sessions.purger_abandonnees(tmp_path)      # ne doit pas lever

    assert {e["session"] for e in emportees} == {"a" * 32, "c" * 32}
    assert not a_dir.exists()
    assert b_dir.exists(), "une session en echec doit rester en place, pas disparaitre a moitie"
    assert not c_dir.exists()


def test_un_fichier_qui_disparait_pendant_le_parcours_ne_bloque_pas_la_session(tmp_path):
    """Une entrée qui disparaît PENDANT le parcours (course avec une autre
    synchro, « .partiel » renommé au même instant) doit être ignorée pour la
    datation, pas faire échouer toute la session — sinon une session qui
    reçoit régulièrement des fichiers éphémères ne serait jamais purgeable :
    chaque passe retomberait sur la même course.
    """
    s = tmp_path / ("f" * 32); s.mkdir()
    (s / "reste.jpg").write_bytes(b"1")
    _vieillir(s, 25 * 3600)
    # Le lien mort est créé APRÈS avoir vieilli : _vieillir() lui-même
    # utilise os.utime(), qui suit les liens par défaut — un lien mort dans
    # l'arborescence AU MOMENT de vieillir ferait lever _vieillir() avant
    # même d'atteindre le code testé.
    (s / "disparu.jpg").symlink_to(tmp_path / "cible-jamais-creee")
    # Créer une entrée dans `s` vient de rafraîchir la date de `s` LUI-MÊME
    # (le dossier a changé de contenu) : la revieillir pour que le test
    # porte bien sur le contenu, pas sur cet effet de bord de la création.
    os.utime(s, (time.time() - 25 * 3600,) * 2)

    emportees = sessions.purger_abandonnees(tmp_path)

    assert [e["session"] for e in emportees] == ["f" * 32]
    assert not s.exists()


def test_un_dossier_qui_n_est_pas_une_session_n_est_jamais_purge(tmp_path):
    """Le filtre est bien `identifiant_valide()`, pas un raccourci du genre
    « ne commence pas par _ » : un dossier ordinaire, vieux lui aussi, doit
    survivre — sinon le seul test sur `_echecs` passerait encore avec un
    filtre plus faible."""
    autre = tmp_path / "Photos"; autre.mkdir(); (autre / "a.jpg").write_bytes(b"1")
    _vieillir(autre, 25 * 3600)

    assert sessions.purger_abandonnees(tmp_path) == []
    assert (autre / "a.jpg").exists()


# --- relecture finale, I2 : une purge reste traçable fichier par fichier ----


def test_la_purge_annonce_chaque_fichier_avant_de_le_supprimer(tmp_path):
    """I2 : avant le `rmtree`, l'appelant reçoit la liste nominative des
    fichiers (chemin relatif à la session, taille) — pendant qu'ils
    existent ENCORE. Sans elle, le journal ne gardait qu'un compte (« 12
    fichier(s) ») et « où est passée cette photo » n'avait plus de réponse."""
    s = tmp_path / ("a" * 32); (s / "DCIM" / "Camera").mkdir(parents=True)
    (s / "DCIM" / "Camera" / "x.jpg").write_bytes(b"123")
    (s / "y.mp4.partiel").write_bytes(b"12345")
    _vieillir(s, 25 * 3600)
    vus = []

    def avant_suppression(session, fichiers):
        encore_la = all((s / chemin).exists() for chemin, _ in fichiers)
        vus.append((session, sorted(fichiers), encore_la))

    emportees = sessions.purger_abandonnees(tmp_path, avant_suppression=avant_suppression)

    assert vus == [("a" * 32, [("DCIM/Camera/x.jpg", 3), ("y.mp4.partiel", 5)], True)]
    assert emportees == [{"session": "a" * 32, "fichiers": 2, "octets": 8}]
    assert not s.exists()


def test_une_session_recente_n_est_pas_annoncee(tmp_path):
    """Seules les sessions réellement supprimées sont annoncées."""
    s = tmp_path / ("b" * 32); s.mkdir(); (s / "y.jpg").write_bytes(b"1")
    vus = []
    sessions.purger_abandonnees(tmp_path, avant_suppression=lambda *a: vus.append(a))
    assert vus == [] and s.exists()


def test_abandonner_annonce_chaque_fichier_avant_de_le_supprimer(tmp_path):
    """I2, même règle pour le bouton « Interrompre » (POST /sync/abandon)."""
    s = tmp_path / ("d" * 32); (s / "DCIM").mkdir(parents=True)
    (s / "DCIM" / "a.jpg").write_bytes(b"12345")
    vus = []

    def avant_suppression(session, fichiers):
        vus.append((session, fichiers, (s / "DCIM" / "a.jpg").exists()))

    resultat = sessions.abandonner(tmp_path, "d" * 32, avant_suppression=avant_suppression)

    assert vus == [("d" * 32, [("DCIM/a.jpg", 5)], True)]
    assert resultat == {"supprimes": 1, "octets": 5}
    assert not s.exists()


def test_abandonner_une_session_sans_dossier_est_quand_meme_annonce(tmp_path):
    """Une session abandonnée avant tout envoi n'a pas de dossier : elle doit
    quand même être annoncée, pour qu'un commit ultérieur soit refusé (M6)."""
    vus = []
    sessions.abandonner(tmp_path, "f" * 32, avant_suppression=lambda *a: vus.append(a))
    assert vus == [("f" * 32, [])]


def test_abandonner_refuse_avant_toute_annonce(tmp_path):
    """Un identifiant hors norme n'est même pas annoncé."""
    vus = []
    with pytest.raises(ValueError):
        sessions.abandonner(tmp_path, "../voisin", avant_suppression=lambda *a: vus.append(a))
    assert vus == []


def test_abandonner_ne_supprime_rien_si_la_session_est_un_lien_symbolique(tmp_path):
    """Un identifiant valide (32 hex) qui désigne un LIEN SYMBOLIQUE n'est
    jamais produit par ce service (`save_upload` ne crée que des dossiers) :
    ne rien supprimer, ne rien compter — plutôt que suivre le lien et rendre
    un bilan qui ment sur ce qui a réellement disparu.
    """
    cible = tmp_path / "ailleurs"; cible.mkdir()
    (cible / "precieux.txt").write_text("a garder")
    lien = tmp_path / ("e" * 32)
    lien.symlink_to(cible, target_is_directory=True)

    resultat = sessions.abandonner(tmp_path, "e" * 32)

    assert resultat == {"supprimes": 0, "octets": 0}
    assert cible.exists() and (cible / "precieux.txt").exists()
    assert lien.exists(), "le lien lui-meme n'a pas a etre retire non plus"
