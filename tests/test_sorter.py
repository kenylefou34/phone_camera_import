import datetime
import pathlib
from mediasort import sorter, dates
from mediasort.catalog import Catalog


def _force_date(monkeypatch, d):
    monkeypatch.setattr(dates, "date_from_metadata", lambda p: d)


def test_sort_places_photo_by_date(tmp_path, monkeypatch):
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.sorted == 1
    assert (lib / "Photos" / "2023" / "05 MAI" / "a.jpg").exists()
    assert not (src / "a.jpg").exists()  # source retirée après copie vérifiée
    cat.close()


def test_sort_dry_run_moves_nothing(tmp_path, monkeypatch):
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=True)

    assert report.sorted == 1  # compté comme "serait rangé"
    assert (src / "a.jpg").exists()  # rien déplacé
    assert not (lib / "Photos").exists()
    cat.close()


def test_sort_skips_duplicate(tmp_path, monkeypatch):
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    (src / "copie.jpg").write_bytes(b"photo-a")  # même contenu
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.sorted == 1
    assert report.duplicates == 1
    cat.close()


def test_sort_unknown_date_goes_to_triage(tmp_path, monkeypatch):
    _force_date(monkeypatch, None)
    monkeypatch.setattr(dates, "date_from_filesystem", lambda p: None)
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "mystere.jpg").write_bytes(b"x")
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.to_triage == 1
    assert (lib / "_A_TRIER" / "mystere.jpg").exists()
    cat.close()


def _compter_hash_complets(monkeypatch):
    """Espionne file_hash dans le trieur et renvoie la liste des fichiers hachés."""
    appels = []
    vrai_hash = sorter.file_hash

    def espion(path):
        appels.append(pathlib.Path(path).name)
        return vrai_hash(path)

    monkeypatch.setattr(sorter, "file_hash", espion)
    return appels


def test_sort_skips_full_hash_when_signature_unknown(tmp_path, monkeypatch):
    """Pré-filtre : signature inconnue => le fichier n'est pas haché en entier."""
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "grosse-video.mp4").write_bytes(b"video" * 1000)
    cat = Catalog(":memory:")  # vide => signatures complètes, pré-filtre actif
    appels = _compter_hash_complets(monkeypatch)

    report = sorter.sort_folder(src, lib, cat, dry_run=True)

    assert report.sorted == 1
    assert appels == []  # aucun hachage complet : la signature a suffi
    cat.close()


def test_sort_still_detects_duplicate_with_prefilter(tmp_path, monkeypatch):
    """Pré-filtre actif : un vrai doublon est toujours reconnu (hash complet fait)."""
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    (src / "copie.jpg").write_bytes(b"photo-a")  # même contenu
    cat = Catalog(":memory:")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.sorted == 1
    assert report.duplicates == 1
    assert cat.signatures_complete() is True  # la signature est enregistrée au rangement
    cat.close()


def test_sort_detects_duplicate_when_catalog_has_no_signatures(tmp_path, monkeypatch):
    """Garde-fou : sur un vieux catalogue sans signatures, le pré-filtre est désactivé.

    Sans ce garde-fou, le doublon passerait inaperçu et serait copié en double.
    """
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")
    # Ligne d'ancien format : empreinte connue, mais aucune signature.
    from mediasort.hashing import file_hash
    cat.add_media(file_hash(src / "a.jpg"), 7, "/lib/deja.jpg", None, "seed")
    assert cat.signatures_complete() is False

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.duplicates == 1
    assert report.sorted == 0
    cat.close()


def test_sort_does_not_hash_the_source_twice(tmp_path, monkeypatch):
    """La source n'est plus hachée séparément : l'empreinte vient de la copie."""
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "grosse-video.mp4").write_bytes(b"video" * 1000)
    cat = Catalog(":memory:")
    haches = []
    vrai_hash = sorter.file_hash
    monkeypatch.setattr(sorter, "file_hash",
                        lambda p: (haches.append(pathlib.Path(p)), vrai_hash(p))[1])

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.sorted == 1
    # Seule la destination est relue pour vérifier la copie.
    assert all(lib in chemin.parents for chemin in haches), haches
    assert len(haches) == 1
    cat.close()


def test_sort_keeps_source_when_copy_is_corrupted(tmp_path, monkeypatch):
    """Copie corrompue : erreur comptée, source CONSERVÉE, rien au catalogue."""
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")
    # La relecture de la destination ne correspond pas à ce qui a été copié.
    monkeypatch.setattr(sorter, "file_hash", lambda p: "empreinte-corrompue")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.errors == 1
    assert (src / "a.jpg").exists()  # la source n'est JAMAIS supprimée sur erreur
    assert cat.count() == 0
    assert list(lib.rglob("*.jpg")) == []  # pas de copie douteuse laissée en biblio
    cat.close()


def test_sort_keeps_source_when_it_changes_during_copy(tmp_path, monkeypatch):
    """Source modifiée entre le contrôle anti-doublon et la copie : erreur, source gardée."""
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")
    cat.add_media("autre-media", 1, "/lib/z.jpg", None, "seed")  # sans signature
    assert cat.signatures_complete() is False  # pré-filtre off => empreinte connue
    def copie_dune_source_modifiee(source, destination):
        destination.write_bytes(b"contenu-different")  # la copie a bien lieu
        return "empreinte-differente"

    monkeypatch.setattr(sorter, "copy_and_hash", copie_dune_source_modifiee)

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.errors == 1
    assert (src / "a.jpg").exists()
    assert cat.count() == 1  # rien d'ajouté
    assert list(lib.rglob("*.jpg")) == []  # pas de copie douteuse laissée en biblio
    cat.close()


def test_retirer_copie_douteuse_tolere_un_fichier_absent(tmp_path):
    """Le nettoyage ne doit jamais lever : sinon l'erreur serait comptée deux fois."""
    sorter._retirer_copie_douteuse(tmp_path / "jamais-ecrit.jpg")  # ne lève pas


def test_report_nomme_les_fichiers_en_echec(tmp_path, monkeypatch):
    """Un échec n'est pas qu'un compteur : le bilan dit QUEL fichier et POURQUOI.

    Sans cette liste, impossible de mettre en quarantaine les seuls fichiers en
    échec : ce qui reste dans le dossier de session contient aussi les doublons
    et le bruit exclu, qu'on a raison de détruire (issue #16).
    """
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "sous").mkdir()
    (src / "sous" / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")
    monkeypatch.setattr(sorter, "file_hash", lambda p: "empreinte-corrompue")

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.errors == 1
    assert len(report.echecs) == 1
    echec = report.echecs[0]
    # Chemin RELATIF au dossier trié : c'est ce dont la quarantaine a besoin
    # pour reconstruire l'arborescence, et c'est affichable sans divulguer les
    # chemins absolus du serveur.
    assert echec["fichier"] == "sous/a.jpg"
    assert "empreinte" in echec["raison"]
    assert report.to_dict()["echecs"] == report.echecs
    cat.close()


def test_report_nomme_l_echec_d_une_source_modifiee(tmp_path, monkeypatch):
    """Deuxième chemin d'erreur : la source change entre le contrôle et la copie."""
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")
    cat.add_media("autre-media", 1, "/lib/z.jpg", None, "seed")  # pré-filtre off
    def copie_dune_source_modifiee(source, destination):
        destination.write_bytes(b"contenu-different")
        return "empreinte-differente"
    monkeypatch.setattr(sorter, "copy_and_hash", copie_dune_source_modifiee)

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.errors == 1
    assert [e["fichier"] for e in report.echecs] == ["a.jpg"]
    assert "source" in report.echecs[0]["raison"]
    cat.close()


def test_report_nomme_l_echec_d_une_erreur_systeme(tmp_path, monkeypatch):
    """Troisième chemin d'erreur : OSError (disque plein, fichier illisible)."""
    _force_date(monkeypatch, datetime.date(2023, 5, 26))
    src = tmp_path / "src"; src.mkdir()
    lib = tmp_path / "lib"; lib.mkdir()
    (src / "a.jpg").write_bytes(b"photo-a")
    cat = Catalog(":memory:")
    def disque_plein(source, destination):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(sorter, "copy_and_hash", disque_plein)

    report = sorter.sort_folder(src, lib, cat, dry_run=False)

    assert report.errors == 1
    assert [e["fichier"] for e in report.echecs] == ["a.jpg"]
    assert "space" in report.echecs[0]["raison"]
    cat.close()
