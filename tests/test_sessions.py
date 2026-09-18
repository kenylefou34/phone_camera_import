import io

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
