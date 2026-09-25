# Galerie de consultation (serveur) — plan d'implémentation

> **Pour les agents :** SOUS-COMPÉTENCE REQUISE : utiliser
> superpowers:subagent-driven-development (recommandé) ou
> superpowers:executing-plans pour dérouler ce plan tâche par tâche. Les
> étapes utilisent des cases à cocher (`- [ ]`).

**Objectif :** une galerie web en lecture seule sur le NUC — années → mois →
jours → grille → média en grand, filtres par dates, type et origine — nourrie
par un recensement de fond qui fabrique les vignettes et comble les dates de
prise de vue manquantes du catalogue.

**Architecture :** quatre modules purs et testables (`classement` déduit
type/origine/date d'un chemin, `galerie_index` tient l'index en mémoire et les
filtres, `galerie_vue` fabrique le modèle d'une page, `vignettes` garde la
table des vignettes), un module qui appelle `exiftool`/`ffmpeg`
(`fabrique`), un processus de fond séparé (`recensement`, son propre service
systemd, `nice` 19, E/S au repos), et des routes FastAPI qui ne font que lire.
**Rien n'écrit jamais dans la bibliothèque** ; seules écritures : la base
`~/phototheque_galerie.db`, les fichiers de vignettes sous
`~/.local/share/phototheque/vignettes/`, et la colonne `date_prise` du
catalogue quand elle est vide.

**Pile :** Python 3.14 (NUC) / 3.10 (poste), FastAPI 0.141, Starlette 1.6
(`FileResponse` gère `Range`), SQLite, `exiftool`, `ffmpeg` 8 (encodeur
`libwebp` présent sur le NUC), pytest.

**Spec :** `docs/superpowers/specs/2026-09-21-galerie-consultation-design.md`
— lire aussi la section « Amendements à la spec » ci-dessous, qui la corrige
sur des mesures faites le 25/09.

**Hors de ce plan :** l'onglet `WebView` de l'application (spec §8). C'est un
second sous-système (Kotlin) ; il fera l'objet d'un plan à part, une fois
cette galerie en service. Ce plan lui prépare seulement le terrain côté
serveur : les routes de lecture acceptent aussi le jeton d'appareil
(`require_lecteur`, tâche 7).

---

## Mesures faites avant d'écrire ce plan (25/09, sur le NUC, lecture seule)

La spec (§11) demandait de mesurer avant d'écrire la moindre ligne.

| Mesure | Résultat |
|---|---|
| Médias au catalogue | **45 643**, dont **44 665** sans `date_prise` (`source_date='seed'`) |
| Chemins au format canonique `[WhatsApp/]Photos\|Videos/AAAA/MM MOIS/fichier` | **37 897 (83 %)** — voir amendement 1 |
| Échantillon de 300 JPEG **tirés au hasard** (`ORDER BY random()`) | **73 %** ont une vignette EXIF (médiane 14 Ko, ~160 px), 16 % un aperçu plus grand, **75 %** une `DateTimeOriginal` |
| Lecture des seuls en-têtes par `exiftool` | **0,14 s par fichier** (41,8 s pour 300) sur le disque NTFS |
| Estimation du recensement complet | ~1 h 45 d'en-têtes + ~11 000 photos à lire en entier (~1 h 30) + 3 650 vidéos (début seulement) ≈ **5 h** — une nuit |
| Disque système | 68 Go libres sur `/` ; vignettes prévues ~1,1 Go |
| Médias sous `_A_TRIER` | **0** (question ouverte n° 2 de la spec : sans objet aujourd'hui, et le code ne les exclut pas) |
| Extensions | `.jpg` 40 383, `.mp4` 3 613, `.jpeg` 674, `.png` 410, `.avi` 208, `.m4v` 159, `.mov` 113, `.webp` 48, `.3gp` 24, `.bmp` 7, `.heic` 3, `.dng` 1 |

## Amendements à la spec (à valider par le mainteneur en relisant ce plan)

1. **17 % des chemins ne suivent pas le format canonique.** Ils se répartissent
   en trois familles :
   - des dossiers d'événements datés dans leur nom (`Photos/2014-10 - A&K -
     Mariage/…`, 3 158 fichiers ; `Photos/2003 - Photos Michèle/…`) ;
   - des sous-dossiers à l'intérieur d'un mois (`Photos/2017/06 JUIN/Mariage
     SetA/…`), ou un mois nommé (`Photos/2022/02 - CANARIAS/…`) ;
   - des dossiers sans aucune date (`Documents/…` 1 615, `unsorted/…` 1 004,
     `Photos/Divers/…` 492…).

   La spec (§9.1) supposait « année, mois et type se déduisent du chemin ». Ce
   plan retient :
   - la **date de prise de vue** d'abord, quand le catalogue la connaît ;
   - sinon la **première année lisible dans le chemin**, avec le mois qui la
     suit s'il y en a un (`2017/06 JUIN/…`, `2022/02 - CANARIAS/…`), ou le
     mois accolé (`2014-10 - …`) ;
   - sinon un rayon **« Sans date »**, toujours visible (tâche 1).

   L'**origine** prend trois valeurs, pas deux : `appareil` (sous `Photos/`
   ou `Videos/`), `whatsapp` (un dossier du chemin contient « whatsapp »),
   `autre` (`Documents/`, `unsorted/`…). Le recensement comblant les dates,
   le rayon « Sans date » fondra de lui-même.
2. **Une vignette EXIF fait environ 160 px, pas 400.** L'agrandir la rendrait
   floue. Elle est donc gardée à sa taille, jamais agrandie. Seules les
   photos lues en entier et les vidéos donnent une vignette de 400 px. La
   grille affiche des cases de 160 px, où les deux se valent.
3. **La galerie devient `/`, l'administration passe à `/admin`** (spec §3 :
   « nouvelle page d'accueil »). Chaque page a un lien vers l'autre.
4. **Les filtres s'appliquent à un index en mémoire**, bâti par une seule
   lecture SQL du catalogue, plutôt qu'en SQL (spec §5). Année et mois se
   déduisent d'un chemin, ce que SQLite ne sait pas faire proprement. Et
   45 643 lignes tiennent en quelques Mo. L'index est reconstruit quand le
   fichier du catalogue change, au plus toutes les 30 s.
5. **Le recensement est un service systemd à part**
   (`phototheque-recensement.service`), pas un fil du serveur web. Ça donne
   un `nice` réel, l'isolement en cas de plantage, et un seul exemplaire à la
   fois (verrou de fichier). Il ne s'arrête jamais : une fois l'arriéré fini,
   il repasse toutes les 10 minutes pour les médias nouvellement importés.
6. **Dates récoltées** : écrites dans `date_prise` seulement si elle est vide,
   avec `source_date` à `metadata` ou `filename` (le vocabulaire du trieur).
   Jamais la date système du fichier (`filesystem`) : sur une bibliothèque
   copiée d'un disque à l'autre, elle ne dit que la date de la copie.

## Contraintes globales

- Documentation et commentaires **en français** ; le mainteneur débute en Python.
- Messages de commit **sans accents**, par heredoc à délimiteur quoté (`git commit -F - <<'FIN'`).
- Terminer chaque message de commit par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Lecture seule sur la bibliothèque** : aucun fichier sous `LIBRARY_DIR` n'est créé, modifié ou supprimé.
- **Jamais un chemin fourni par le client** : on résout une empreinte (64 hexadécimaux) par le catalogue, puis on vérifie que le chemin obtenu est sous `LIBRARY_DIR` (spec §7).
- **Jamais un fichier entier en mémoire** pour servir un média (leçon de l'issue #21).
- `exiftool` et `ffmpeg` seulement, **aucune dépendance Python nouvelle**.
- Vignettes : 400 px de côté au plus, WebP ; taille intermédiaire 1280 px à la demande, photos seulement.
- Routes derrière `require_admin` ou le jeton d'appareil ; **`/docs`, `/redoc`, `/openapi.json` restent en 404** (revérifier à chaque route ajoutée).
- NUC : 2 cœurs, 3 Go, disque Famille à ~7 Mo/s — la synchronisation du téléphone reste prioritaire.
- Tests serveur : `python3 -m pytest -q` ; chaque nouveau test est **validé par mutation** (casser le code, voir CE test tomber).

## Points de vigilance à la relecture

Les cinq cas que la spec implique sans les nommer, les plus probables d'abord.
Chacun est épinglé par un test dans la tâche indiquée.

1. **Des noms de fichiers avec `&`, `'`, `<`, accents et espaces** (`A&K`,
   `Michèle`, `Les Bouchons d'Aur`) : pages et liens doivent échapper. Test :
   tâche 8, `test_un_nom_piege_est_echappe_partout`.
2. **Un chemin de catalogue qui ne mène plus à rien**, parce que le
   mainteneur a déplacé un dossier curaté à la main. `/galerie/original`
   répond 404, sans lever ; le recensement note « fichier absent » et
   continue. Tests : tâche 6, `test_un_fichier_disparu_est_note_et_la_passe_continue` ;
   tâche 7, `test_original_d_un_fichier_disparu_repond_404`.
3. **Des dates de métadonnées absurdes** (`0000:00:00 00:00:00`, fréquente sur
   les vieux appareils) : ne jamais les écrire dans `date_prise`, retomber sur
   le nom du fichier. Test : tâche 6, `test_une_date_nulle_ne_s_ecrit_pas`.
4. **Les fichiers `._nom.mp4`** (restes AppleDouble d'un Mac, présents dans
   `Videos/2018-10 - Ken competition/`) : ce ne sont pas des médias, ils
   n'entrent pas dans l'index. Test : tâche 1,
   `test_un_reste_appledouble_n_est_pas_un_media`.
5. **Un mois de 3 158 photos** (le mariage) : la grille reste paginée à 120,
   et les liens de page gardent les filtres. Test : tâche 3,
   `test_la_pagination_garde_les_filtres`.

---

## Carte des fichiers

| Fichier | Rôle |
|---|---|
| `phototheque/classement.py` (nouveau) | Pur : `classer(chemin, date_prise, bibliotheque) -> Classement \| None` |
| `phototheque/galerie_index.py` (nouveau) | `Media`, `Filtres`, `Index` (filtres, comptes, sélection), cache `index_courant` |
| `phototheque/galerie_vue.py` (nouveau) | Pur : lecture des paramètres d'URL, `url(...)`, libellés français, `construire_vue(...) -> VueGalerie` |
| `phototheque/vignettes.py` (nouveau) | Table `vignettes` (base `GALERIE_DB`), chemins des fichiers de vignettes, `EMPREINTE` |
| `phototheque/fabrique.py` (nouveau) | Appels `exiftool`/`ffmpeg`/`ffprobe` : métadonnées par lot, vignette, taille intermédiaire |
| `phototheque/recensement.py` (nouveau) | La passe reprenable + le démon (`python3 -m phototheque.recensement`) |
| `phototheque/config.py` | + `GALERIE_DB`, `VIGNETTES_DIR` |
| `phototheque/app.py` | + `require_lecteur`, `_media_sur`, routes `/`, `/admin`, `/galerie/…` |
| `phototheque/web.py` | + `galerie_html`, `media_html`, bloc « Galerie » de l'admin ; liens « Retour » → `/admin` |
| `deploy/phototheque-recensement.service` (nouveau) | Unité systemd du recensement |
| `deploy/install.sh` | Installe et (re)démarre la seconde unité |
| `tests/test_classement.py`, `tests/test_galerie_index.py`, `tests/test_galerie_vue.py`, `tests/test_vignettes.py`, `tests/test_fabrique.py`, `tests/test_recensement.py`, `tests/test_galerie_routes.py` (nouveaux) | Tests |
| `tests/test_app.py`, `tests/test_deploy.py` | Adresses d'admin, unité systemd |
| `docs/DEPLOIEMENT.md`, `CLAUDE.md` | Mode d'emploi, état |

---

### Tâche 1 : classer un média d'après son chemin et sa date

**Fichiers :**
- Créer : `phototheque/classement.py`
- Test : `tests/test_classement.py`

**Interfaces :**
- Consomme : `mediasort.classify.media_type(ext: str) -> "photo" | "video" | None`
- Produit :
  - `classement.APPAREIL`, `WHATSAPP`, `AUTRE` (chaînes) ;
  - `Classement(type, origine, annee, mois, jour, source)` (dataclass figée ; `source` vaut `"date_prise"`, `"chemin"` ou `"aucune"`) ;
  - `classer(chemin: str, date_prise: str | None, bibliotheque: str) -> Classement | None`.

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
"""Tests du classement galerie : type, origine et date déduits du chemin."""
from phototheque.classement import APPAREIL, AUTRE, WHATSAPP, classer

BIB = "/media/izquierdo/Famille"


def _c(rel, date_prise=None):
    return classer(f"{BIB}/{rel}", date_prise, BIB)


def test_chemin_canonique_photo():
    c = _c("Photos/2013/05 MAI/IMG_1.jpg")
    assert (c.type, c.origine, c.annee, c.mois, c.jour, c.source) == \
        ("photo", APPAREIL, 2013, 5, None, "chemin")


def test_chemin_canonique_video_whatsapp():
    c = _c("WhatsApp/Videos/2023/06 JUIN/VID-20230625-WA0001.mp4")
    assert (c.type, c.origine, c.annee, c.mois) == ("video", WHATSAPP, 2023, 6)


def test_mois_ecrit_avec_deux_espaces():
    # Réel : « WhatsApp/Photos/2013/10  OCTOBRE/ » existe sur le NUC.
    assert _c("WhatsApp/Photos/2013/10  OCTOBRE/IMG-1.jpg").mois == 10


def test_dossier_d_evenement_date_dans_son_nom():
    c = _c("Photos/2014-10 - A&K - Mariage/LM Noir&Blanc Facebook/AK-2377.jpg")
    assert (c.annee, c.mois, c.origine) == (2014, 10, APPAREIL)


def test_annee_seule_dans_le_nom_d_un_dossier():
    c = _c("Photos/2003 - Photos Michèle/mon album 142.jpg")
    assert (c.annee, c.mois) == (2003, None)


def test_mois_nomme_apres_une_annee():
    assert (_c("Photos/2022/02 - CANARIAS/IMG_1.jpg").annee,
            _c("Photos/2022/02 - CANARIAS/IMG_1.jpg").mois) == (2022, 2)


def test_sous_dossier_dans_un_mois():
    c = _c("Photos/2017/06 JUIN/Mariage SetA/0246Flo.JPG")
    assert (c.annee, c.mois) == (2017, 6)


def test_annee_sans_mois():
    c = _c("Videos/2020/VID_20200806_164934.mp4")
    assert (c.annee, c.mois, c.type) == (2020, None, "video")


def test_dossier_sans_date_va_dans_sans_date_origine_autre():
    c = _c("Documents/LA CIGALIERE/Divers/jpd firma.jpg")
    assert (c.annee, c.mois, c.jour, c.source, c.origine) == \
        (None, None, None, "aucune", AUTRE)


def test_whatsapp_meme_sous_unsorted():
    assert _c("unsorted/WhatsApp/Media/x/VID-20231105-WA0000.mp4").origine == WHATSAPP


def test_la_date_de_prise_prime_sur_le_chemin():
    c = _c("Photos/2014-10 - A&K - Mariage/AK-1.jpg", date_prise="2014-10-18")
    assert (c.annee, c.mois, c.jour, c.source) == (2014, 10, 18, "date_prise")


def test_une_date_de_prise_illisible_retombe_sur_le_chemin():
    c = _c("Photos/2013/05 MAI/IMG_1.jpg", date_prise="0000-00-00")
    assert (c.annee, c.mois, c.jour, c.source) == (2013, 5, None, "chemin")


def test_extension_non_geree_n_est_pas_un_media():
    assert _c("Documents/plaquette.pdf") is None


def test_un_reste_appledouble_n_est_pas_un_media():
    # Point de vigilance n° 4 : « ._Combat Philou….mp4 » existe sur le NUC.
    assert _c("Videos/2018-10 - Ken competition/._Combat.mp4") is None


def test_extension_en_majuscules():
    assert _c("Videos/2015/09 SEPTEMBRE/HDV_0495.MP4").type == "video"


def test_chemin_hors_bibliotheque_reste_classable():
    c = classer("/ailleurs/Photos/2019/01 JANVIER/a.jpg", None, BIB)
    assert (c.annee, c.mois) == (2019, 1)
```

- [ ] **Étape 2 : lancer les tests pour les voir échouer**

Lancer : `python3 -m pytest tests/test_classement.py -q`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'phototheque.classement'`

- [ ] **Étape 3 : écrire le module**

```python
"""Classement d'un média pour la galerie : type, origine, année/mois/jour.

Lecture seule : ce module ne touche ni au disque ni au catalogue. Tout se
déduit du chemin rangé et, quand le catalogue la connaît, de la date de prise
de vue.

Pourquoi pas seulement le chemin ? Parce que 17 % de la bibliothèque (mesure
du 25/09) n'est pas rangée au format « Photos/AAAA/MM MOIS/ » : dossiers
d'événements (« 2014-10 - A&K - Mariage »), sous-dossiers dans un mois,
dossiers sans date (« Documents », « unsorted »). Aucun ne doit disparaître de
la galerie : ce qui n'a pas de date va dans le rayon « Sans date ».
"""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from mediasort.classify import media_type

# Les trois origines proposées par le filtre « Origine ».
APPAREIL, WHATSAPP, AUTRE = "appareil", "whatsapp", "autre"

# « 2014-10-18 » : la forme écrite par le trieur dans `date_prise`.
_DATE_PRISE = re.compile(r"^((?:19|20)\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
# « 2013 » : un dossier d'année.
_ANNEE = re.compile(r"^((?:19|20)\d{2})$")
# « 2014-10 - A&K - Mariage » : événement daté au mois.
_ANNEE_MOIS_NOMME = re.compile(r"^((?:19|20)\d{2})-(0[1-9]|1[0-2])(?:\s|$)")
# « 2003 - Photos Michèle » : événement daté à l'année.
_ANNEE_NOMMEE = re.compile(r"^((?:19|20)\d{2})\s+-\s")
# « 05 MAI », « 10  OCTOBRE », « 02 - CANARIAS » : le dossier qui suit une année.
_MOIS = re.compile(r"^(0[1-9]|1[0-2])(?:\s|$)")


@dataclass(frozen=True, slots=True)
class Classement:
    """Ce que la galerie sait d'un média. `None` = inconnu."""
    type: str            # "photo" ou "video"
    origine: str         # APPAREIL, WHATSAPP ou AUTRE
    annee: int | None
    mois: int | None
    jour: int | None
    source: str          # "date_prise", "chemin" ou "aucune"


def _dossiers(chemin: str, bibliotheque: str) -> tuple[str, ...]:
    """Les dossiers du chemin, relatifs à la bibliothèque, sans le nom du fichier."""
    p = PurePosixPath(chemin)
    try:
        rel = p.relative_to(bibliotheque)
    except ValueError:
        # Hors bibliothèque (ne devrait pas arriver) : on garde tout sauf la racine.
        rel = PurePosixPath(*p.parts[1:]) if p.is_absolute() else p
    return rel.parts[:-1]


def _origine(dossiers: tuple[str, ...]) -> str:
    if any("whatsapp" in d.lower() for d in dossiers):
        return WHATSAPP
    if dossiers and dossiers[0] in ("Photos", "Videos"):
        return APPAREIL
    return AUTRE


def _date_du_chemin(dossiers: tuple[str, ...]) -> tuple[int | None, int | None]:
    """(année, mois) lus dans le premier dossier daté du chemin."""
    for i, d in enumerate(dossiers):
        m = _ANNEE.match(d)
        if m:
            suivant = dossiers[i + 1] if i + 1 < len(dossiers) else ""
            mm = _MOIS.match(suivant)
            return int(m.group(1)), (int(mm.group(1)) if mm else None)
        m = _ANNEE_MOIS_NOMME.match(d)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = _ANNEE_NOMMEE.match(d)
        if m:
            return int(m.group(1)), None
    return None, None


def classer(chemin: str, date_prise: str | None, bibliotheque: str) -> Classement | None:
    """Classe un média ; `None` si ce n'est pas un média affichable."""
    nom = PurePosixPath(chemin).name
    if nom.startswith("._"):
        # Reste AppleDouble laissé par un Mac : des métadonnées, pas un média.
        return None
    type_ = media_type(PurePosixPath(chemin).suffix)
    if type_ is None:
        return None
    dossiers = _dossiers(chemin, bibliotheque)
    origine = _origine(dossiers)
    m = _DATE_PRISE.match(date_prise or "")
    if m:
        annee, mois, jour = (int(g) for g in m.groups())
        return Classement(type_, origine, annee, mois, jour, "date_prise")
    annee, mois = _date_du_chemin(dossiers)
    if annee is not None:
        return Classement(type_, origine, annee, mois, None, "chemin")
    return Classement(type_, origine, None, None, None, "aucune")
```

- [ ] **Étape 4 : lancer les tests pour les voir passer**

Lancer : `python3 -m pytest tests/test_classement.py -q`
Attendu : `16 passed`

- [ ] **Étape 5 : valider par mutation**

Casser tour à tour, en relançant le fichier de tests à chaque fois (puis
remettre) :
- supprimer le test `nom.startswith("._")` → `test_un_reste_appledouble…` doit tomber ;
- remplacer `(?:\s|$)` par ` ` dans `_MOIS` → `test_mois_ecrit_avec_deux_espaces` doit tomber ;
- inverser l'ordre date de prise / chemin → `test_la_date_de_prise_prime…` doit tomber.

- [ ] **Étape 6 : commit**

```bash
git add phototheque/classement.py tests/test_classement.py
git commit -F - <<'FIN'
feat(galerie): classer un media d'apres son chemin et sa date (#31)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Tâche 2 : l'index en mémoire et ses filtres

**Fichiers :**
- Créer : `phototheque/galerie_index.py`
- Test : `tests/test_galerie_index.py`

**Interfaces :**
- Consomme : `classement.classer`, `classement.Classement`
- Produit :
  - `SANS = "sans"` (la valeur « inconnu » dans une sélection) ;
  - `Media(empreinte, chemin, taille, c)` avec la propriété `.nom` ;
  - `Filtres(du: date|None, au: date|None, type: str|None, origine: str|None)` ;
  - `Index(medias)` : `depuis_catalogue(catalog_db, bibliotheque)` (méthode de classe), `tous()`, `trouver(empreinte)`, `filtrer(f)`, `compter_annees(f)`, `compter_mois(f, annee)`, `compter_jours(f, annee, mois)`, `selectionner(f, annee, mois=None, jour=None)` ;
  - `index_courant(catalog_db, bibliotheque, maintenant=time.monotonic) -> Index` et `vider_cache()`.

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
"""Tests de l'index galerie : filtres, comptes, sélection, cache."""
import os
import sqlite3
from datetime import date

from mediasort.catalog import Catalog
from phototheque import galerie_index as gi
from phototheque.classement import classer

BIB = "/bib"


def _m(empreinte, rel, date_prise=None, taille=1):
    ch = f"{BIB}/{rel}"
    return gi.Media(empreinte, ch, taille, classer(ch, date_prise, BIB))


def _index():
    return gi.Index([
        _m("a", "Photos/2023/06 JUIN/IMG_1.jpg", "2023-06-21"),
        _m("b", "Photos/2023/06 JUIN/IMG_2.jpg", "2023-06-15"),
        _m("c", "Photos/2023/06 JUIN/IMG_3.jpg"),                 # jour inconnu
        _m("d", "Videos/2023/07 JUILLET/VID_1.mp4"),
        _m("e", "WhatsApp/Photos/2022/01 JANVIER/IMG-1.jpg"),
        _m("f", "Documents/x/logo.png"),                          # sans date
    ])


def test_compter_les_annees_du_plus_recent_au_plus_ancien_puis_sans_date():
    assert _index().compter_annees(gi.Filtres()) == [(2023, 4), (2022, 1), (gi.SANS, 1)]


def test_compter_les_mois_d_une_annee():
    assert _index().compter_mois(gi.Filtres(), 2023) == [(7, 1), (6, 3)]


def test_compter_les_jours_met_le_jour_inconnu_en_dernier():
    assert _index().compter_jours(gi.Filtres(), 2023, 6) == [(15, 1), (21, 1), (gi.SANS, 1)]


def test_un_media_sans_date_prise_reste_dans_son_mois():
    # Spec §9.2 : c'est le cas de 98 % de la bibliothèque, pas un cas dégradé.
    noms = [m.empreinte for m in _index().selectionner(gi.Filtres(), 2023, 6)]
    assert noms == ["b", "a", "c"], "jour connu d'abord (15 puis 21), inconnu ensuite"


def test_selectionner_le_rayon_sans_date():
    assert [m.empreinte for m in _index().selectionner(gi.Filtres(), gi.SANS)] == ["f"]


def test_filtre_type():
    assert [m.empreinte for m in _index().filtrer(gi.Filtres(type="video"))] == ["d"]


def test_filtre_origine():
    assert [m.empreinte for m in _index().filtrer(gi.Filtres(origine="whatsapp"))] == ["e"]


def test_filtre_dates_sur_un_jour_connu():
    f = gi.Filtres(du=date(2023, 6, 16), au=date(2023, 6, 30))
    assert "a" in [m.empreinte for m in _index().filtrer(f)]
    assert "b" not in [m.empreinte for m in _index().filtrer(f)]


def test_filtre_dates_garde_un_media_dont_seul_le_mois_est_connu():
    # « Reproposer plutôt que sauter » : juin chevauche l'intervalle, on le garde.
    f = gi.Filtres(du=date(2023, 6, 16), au=date(2023, 6, 30))
    assert "c" in [m.empreinte for m in _index().filtrer(f)]


def test_filtre_dates_ecarte_le_sans_date():
    f = gi.Filtres(du=date(2000, 1, 1))
    assert "f" not in [m.empreinte for m in _index().filtrer(f)]


def test_une_date_de_prise_impossible_ne_plante_pas_le_filtre():
    ix = gi.Index([_m("z", "Photos/2023/02 FEVRIER/a.jpg", "2023-02-30")])
    assert ix.filtrer(gi.Filtres(du=date(2023, 2, 1), au=date(2023, 2, 28))) != []


def _catalogue(tmp_path, lignes):
    cat = Catalog(tmp_path / "cat.db")
    for e, ch, dp in lignes:
        cat.add_media(e, 10, ch, dp, "seed" if dp is None else "metadata")
    cat.close()
    return tmp_path / "cat.db"


def test_depuis_catalogue_ignore_ce_qui_n_est_pas_un_media(tmp_path):
    db = _catalogue(tmp_path, [
        ("a" * 64, f"{BIB}/Photos/2023/06 JUIN/IMG_1.jpg", None),
        ("b" * 64, f"{BIB}/Documents/plaquette.pdf", None),
    ])
    ix = gi.Index.depuis_catalogue(db, BIB)
    assert [m.empreinte for m in ix.tous()] == ["a" * 64]
    assert ix.trouver("a" * 64).c.annee == 2023


def test_le_cache_se_reconstruit_quand_le_catalogue_change(tmp_path):
    gi.vider_cache()
    db = _catalogue(tmp_path, [("a" * 64, f"{BIB}/Photos/2023/06 JUIN/1.jpg", None)])
    horloge = [1000.0]
    assert len(gi.index_courant(db, BIB, maintenant=lambda: horloge[0])) == 1
    cat = Catalog(db)
    cat.add_media("b" * 64, 10, f"{BIB}/Photos/2023/06 JUIN/2.jpg", None, "seed")
    cat.close()
    st = os.stat(db)
    os.utime(db, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    horloge[0] += 5                       # trop tôt : on garde l'ancien index
    assert len(gi.index_courant(db, BIB, maintenant=lambda: horloge[0])) == 1
    horloge[0] += 60                      # délai passé : on reconstruit
    assert len(gi.index_courant(db, BIB, maintenant=lambda: horloge[0])) == 2


def test_catalogue_absent_donne_un_index_vide(tmp_path):
    gi.vider_cache()
    assert len(gi.index_courant(tmp_path / "absent.db", BIB)) == 0
```

- [ ] **Étape 2 : lancer les tests pour les voir échouer**

Lancer : `python3 -m pytest tests/test_galerie_index.py -q`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'phototheque.galerie_index'`

- [ ] **Étape 3 : écrire le module**

```python
"""Index en mémoire des médias du catalogue, pour la galerie (lecture seule).

Une seule requête SQL lit tout le catalogue (45 643 lignes au 25/09, quelques
Mo en mémoire) ; les filtres, les comptes par année/mois/jour et la sélection
d'une grille se font ensuite en Python. Pourquoi pas en SQL ? Parce que
l'année et le mois se déduisent souvent du chemin (voir classement.py), ce
que SQLite ne sait pas faire proprement.

L'index est gardé en cache et reconstruit quand le fichier du catalogue
change — au plus toutes les RAFRAICHISSEMENT_MIN_S secondes, car le
recensement y écrit des dates par petits lots toute la nuit.
"""

import os
import sqlite3
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path, PurePosixPath

from .classement import Classement, classer

# Valeur « inconnu » dans une sélection : le rayon « Sans date », le « Mois
# inconnu » d'une année, le « Jour inconnu » d'un mois.
SANS = "sans"

RAFRAICHISSEMENT_MIN_S = 30


@dataclass(frozen=True, slots=True)
class Media:
    empreinte: str
    chemin: str
    taille: int
    c: Classement

    @property
    def nom(self) -> str:
        return PurePosixPath(self.chemin).name


@dataclass(frozen=True)
class Filtres:
    du: date | None = None
    au: date | None = None
    type: str | None = None       # "photo" ou "video"
    origine: str | None = None    # "appareil", "whatsapp" ou "autre"


def _fin_du_mois(annee: int, mois: int) -> date:
    return date(annee + (mois == 12), mois % 12 + 1, 1) - timedelta(days=1)


def _dans_intervalle(c: Classement, du: date | None, au: date | None) -> bool:
    """Vrai si la période connue du média chevauche [du, au].

    Un média dont seul le mois (ou l'année) est connu est gardé dès que ce
    mois chevauche l'intervalle : mieux vaut le montrer en trop que le cacher.
    Un média sans aucune date est écarté dès qu'un filtre de dates est posé :
    on ne peut pas le placer.
    """
    if du is None and au is None:
        return True
    if c.annee is None:
        return False
    if c.mois is None:
        debut, fin = date(c.annee, 1, 1), date(c.annee, 12, 31)
    else:
        debut, fin = date(c.annee, c.mois, 1), _fin_du_mois(c.annee, c.mois)
        if c.jour is not None:
            try:
                debut = fin = date(c.annee, c.mois, c.jour)
            except ValueError:
                pass      # « 30 février » venu d'un appareil déréglé : on garde le mois
    return (du is None or fin >= du) and (au is None or debut <= au)


def _ordonner(compte: Counter, decroissant: bool) -> list[tuple[int | str, int]]:
    """Clés connues triées, puis la case « inconnu » (SANS) en dernier."""
    connues = sorted((k for k in compte if k is not None), reverse=decroissant)
    resultat: list[tuple[int | str, int]] = [(k, compte[k]) for k in connues]
    if None in compte:
        resultat.append((SANS, compte[None]))
    return resultat


def _garde(valeur: int | None, voulu: int | str | None) -> bool:
    """`voulu` : None = pas de contrainte, SANS = inconnu, sinon égalité."""
    if voulu is None:
        return True
    if voulu == SANS:
        return valeur is None
    return valeur == voulu


class Index:
    def __init__(self, medias: list[Media]):
        self._medias = medias
        self._par_empreinte = {m.empreinte: m for m in medias}

    @classmethod
    def depuis_catalogue(cls, catalog_db: Path, bibliotheque: Path | str) -> "Index":
        # Lecture seule explicite (`mode=ro`) : la galerie n'écrit jamais ici.
        cx = sqlite3.connect(f"file:{catalog_db}?mode=ro", uri=True, timeout=30)
        try:
            lignes = cx.execute(
                "SELECT empreinte, chemin, taille, date_prise FROM medias"
                " WHERE chemin IS NOT NULL").fetchall()
        finally:
            cx.close()
        medias = []
        for empreinte, chemin, taille, date_prise in lignes:
            c = classer(chemin, date_prise, str(bibliotheque))
            if c is not None:
                medias.append(Media(empreinte, chemin, taille or 0, c))
        return cls(medias)

    def __len__(self) -> int:
        return len(self._medias)

    def tous(self) -> list[Media]:
        return list(self._medias)

    def trouver(self, empreinte: str) -> Media | None:
        return self._par_empreinte.get(empreinte)

    def filtrer(self, f: Filtres) -> list[Media]:
        return [m for m in self._medias
                if (f.type is None or m.c.type == f.type)
                and (f.origine is None or m.c.origine == f.origine)
                and _dans_intervalle(m.c, f.du, f.au)]

    def compter_annees(self, f: Filtres) -> list[tuple[int | str, int]]:
        return _ordonner(Counter(m.c.annee for m in self.filtrer(f)), decroissant=True)

    def compter_mois(self, f: Filtres, annee: int) -> list[tuple[int | str, int]]:
        return _ordonner(Counter(m.c.mois for m in self.filtrer(f) if m.c.annee == annee),
                         decroissant=True)

    def compter_jours(self, f: Filtres, annee: int, mois: int) -> list[tuple[int | str, int]]:
        return _ordonner(Counter(m.c.jour for m in self.filtrer(f)
                                 if m.c.annee == annee and m.c.mois == mois),
                         decroissant=False)

    def selectionner(self, f: Filtres, annee: int | str | None,
                     mois: int | str | None = None,
                     jour: int | str | None = None) -> list[Media]:
        """Les médias d'une case, jour connu d'abord puis par nom de fichier
        (qui porte le plus souvent l'heure : IMG_20230625_101500.jpg)."""
        choisis = [m for m in self.filtrer(f)
                   if _garde(m.c.annee, annee) and _garde(m.c.mois, mois)
                   and _garde(m.c.jour, jour)]
        choisis.sort(key=lambda m: (m.c.jour is None, m.c.jour or 0, m.nom))
        return choisis


_cache: dict = {"cle": None, "mtime": None, "index": None, "construit": 0.0}
_verrou = threading.Lock()


def vider_cache() -> None:
    """Pour les tests : oublie l'index gardé en mémoire."""
    with _verrou:
        _cache.update(cle=None, mtime=None, index=None, construit=0.0)


def index_courant(catalog_db: Path, bibliotheque: Path | str,
                  maintenant=time.monotonic) -> Index:
    """L'index du moment, reconstruit si le catalogue a changé (au plus
    toutes les RAFRAICHISSEMENT_MIN_S secondes)."""
    try:
        mtime = os.stat(catalog_db).st_mtime_ns
    except FileNotFoundError:
        return Index([])
    cle = (str(catalog_db), str(bibliotheque))
    with _verrou:
        perime = (_cache["index"] is None or _cache["cle"] != cle
                  or (_cache["mtime"] != mtime
                      and maintenant() - _cache["construit"] >= RAFRAICHISSEMENT_MIN_S))
        if perime:
            _cache.update(cle=cle, mtime=mtime, construit=maintenant(),
                          index=Index.depuis_catalogue(catalog_db, bibliotheque))
        return _cache["index"]
```

- [ ] **Étape 4 : lancer les tests pour les voir passer**

Lancer : `python3 -m pytest tests/test_galerie_index.py -q`
Attendu : `14 passed`

- [ ] **Étape 5 : valider par mutation**

- `_dans_intervalle` : remplacer `return False` (sans date) par `return True` → `test_filtre_dates_ecarte_le_sans_date` tombe ;
- `_ordonner` : oublier d'ajouter `SANS` → `test_compter_les_annees…` tombe ;
- `index_courant` : retirer la condition sur `RAFRAICHISSEMENT_MIN_S` → la ligne « trop tôt » de `test_le_cache_se_reconstruit…` tombe.

- [ ] **Étape 6 : commit**

```bash
git add phototheque/galerie_index.py tests/test_galerie_index.py
git commit -F - <<'FIN'
feat(galerie): index en memoire, filtres et comptes par annee/mois/jour (#31)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Tâche 3 : le modèle d'une page de galerie

**Fichiers :**
- Créer : `phototheque/galerie_vue.py`
- Test : `tests/test_galerie_vue.py`

**Interfaces :**
- Consomme : `galerie_index.Index`, `Filtres`, `Media`, `SANS`
- Produit :
  - `TAILLE_PAGE = 120` ;
  - `lire_filtres(du, au, type_, origine) -> tuple[Filtres, str | None]` ;
  - `lire_niveau(valeur: str) -> int | str | None` ;
  - `url(filtres, annee=None, mois=None, jour=None, page=None) -> str` ;
  - `libelle_annee(a)`, `libelle_mois(m)`, `libelle_jour(a, m, j)` ;
  - `VueGalerie(titre, fil, filtres, blocs, groupes, page, pages, total, precedente, suivante, message)` ;
  - `construire_vue(index, filtres, annee=None, mois=None, jour=None, page=1, message=None) -> VueGalerie`.

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
"""Tests du modèle de page : niveaux, libellés, pagination, filtres."""
from datetime import date
from urllib.parse import parse_qs, urlparse

from phototheque import galerie_index as gi
from phototheque import galerie_vue as gv
from phototheque.classement import classer

BIB = "/bib"


def _m(e, rel, dp=None):
    ch = f"{BIB}/{rel}"
    return gi.Media(e, ch, 1, classer(ch, dp, BIB))


def _index():
    return gi.Index([
        _m("a", "Photos/2023/06 JUIN/IMG_1.jpg", "2023-06-19"),
        _m("b", "Photos/2023/06 JUIN/IMG_2.jpg"),
        _m("c", "Photos/2022/01 JANVIER/IMG_3.jpg"),
        _m("d", "Documents/logo.png"),
    ])


def test_accueil_liste_les_annees_et_le_rayon_sans_date():
    v = gv.construire_vue(_index(), gi.Filtres())
    assert [(lib, n) for lib, _, n in v.blocs] == [("2023", 2), ("2022", 1), ("Sans date", 1)]
    assert v.groupes == []


def test_une_annee_liste_ses_mois_en_francais():
    v = gv.construire_vue(_index(), gi.Filtres(), annee=2023)
    assert [lib for lib, _, _ in v.blocs] == ["Juin"]
    assert [lib for lib, _ in v.fil] == ["Toutes les années", "2023"]


def test_un_mois_avec_des_jours_connus_montre_le_niveau_jours_et_la_grille():
    v = gv.construire_vue(_index(), gi.Filtres(), annee=2023, mois=6)
    assert [lib for lib, _, _ in v.blocs] == ["lundi 19", "Jour inconnu"]
    assert [(titre, [m.empreinte for m in ms]) for titre, ms in v.groupes] == \
        [("lundi 19", ["a"]), ("Jour inconnu", ["b"])]


def test_un_mois_sans_aucun_jour_connu_affiche_sa_grille_directement():
    # Spec §5 : dégradation naturelle, sans message d'erreur.
    v = gv.construire_vue(_index(), gi.Filtres(), annee=2022, mois=1)
    assert v.blocs == []
    assert [m.empreinte for _, ms in v.groupes for m in ms] == ["c"]


def test_le_rayon_sans_date_affiche_sa_grille():
    v = gv.construire_vue(_index(), gi.Filtres(), annee=gi.SANS)
    assert [m.empreinte for _, ms in v.groupes for m in ms] == ["d"]


def test_la_pagination_garde_les_filtres():
    # Point de vigilance n° 5 : le mariage compte 3 158 photos dans un mois.
    ix = gi.Index([_m(f"{i:064x}", f"Photos/2014-10 - Mariage/AK-{i:04d}.jpg")
                   for i in range(300)])
    f = gi.Filtres(type="photo", origine="appareil")
    v = gv.construire_vue(ix, f, annee=2014, mois=10, page=2)
    assert (v.page, v.pages, v.total) == (2, 3, 300)
    assert sum(len(ms) for _, ms in v.groupes) == gv.TAILLE_PAGE
    q = parse_qs(urlparse(v.suivante).query)
    assert q == {"annee": ["2014"], "mois": ["10"], "type": ["photo"],
                 "origine": ["appareil"], "page": ["3"]}
    assert "page" not in parse_qs(urlparse(v.precedente).query), "page 1 = sans « page »"


def test_une_page_hors_limites_est_ramenee_dans_les_bornes():
    v = gv.construire_vue(_index(), gi.Filtres(), annee=2023, mois=6, page=99)
    assert v.page == 1 and v.suivante is None


def test_lire_filtres_ignore_les_valeurs_inconnues():
    f, msg = gv.lire_filtres("pas-une-date", "", "gif", "martien")
    assert f == gi.Filtres() and msg is None


def test_lire_filtres_inverse_des_dates_a_l_envers_et_le_dit():
    f, msg = gv.lire_filtres("2023-12-31", "2023-01-01", "", "")
    assert (f.du, f.au) == (date(2023, 1, 1), date(2023, 12, 31))
    assert "inversées" in msg


def test_lire_niveau():
    assert (gv.lire_niveau(""), gv.lire_niveau("sans"), gv.lire_niveau("2023"),
            gv.lire_niveau("x")) == (None, gi.SANS, 2023, None)


def test_un_jour_impossible_garde_son_numero():
    assert gv.libelle_jour(2023, 2, 30) == "30"
```

- [ ] **Étape 2 : lancer les tests pour les voir échouer**

Lancer : `python3 -m pytest tests/test_galerie_vue.py -q`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'phototheque.galerie_vue'`

- [ ] **Étape 3 : écrire le module**

```python
"""Modèle d'une page de galerie : ce qu'il faut afficher, sans le HTML.

Séparé de web.py pour être testé sans navigateur : quel niveau (années, mois,
grille), quels liens, quelle page. web.py ne fait que mettre ce modèle en
forme.
"""

from dataclasses import dataclass, field
from datetime import date
from math import ceil
from urllib.parse import urlencode

from .galerie_index import SANS, Filtres, Index, Media

TAILLE_PAGE = 120

MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre")
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


@dataclass
class VueGalerie:
    titre: str
    fil: list[tuple[str, str]]                 # fil d'Ariane : (libellé, url)
    filtres: Filtres
    blocs: list[tuple[str, str, int]]          # (libellé, url, nombre)
    groupes: list[tuple[str, list[Media]]] = field(default_factory=list)
    page: int = 1
    pages: int = 1
    total: int = 0
    precedente: str | None = None
    suivante: str | None = None
    message: str | None = None


def lire_filtres(du: str, au: str, type_: str, origine: str) -> tuple[Filtres, str | None]:
    """Traduit les paramètres d'URL. Une valeur inconnue est ignorée, jamais
    une erreur : c'est une page qu'on feuillette, pas un formulaire à corriger."""
    def jour(texte: str) -> date | None:
        try:
            return date.fromisoformat(texte) if texte else None
        except ValueError:
            return None
    debut, fin, message = jour(du), jour(au), None
    if debut and fin and debut > fin:
        debut, fin = fin, debut
        message = "La date de début était après la date de fin : les deux ont été inversées."
    return (Filtres(debut, fin,
                    type_ if type_ in ("photo", "video") else None,
                    origine if origine in ("appareil", "whatsapp", "autre") else None),
            message)


def lire_niveau(valeur: str) -> int | str | None:
    if valeur == SANS:
        return SANS
    try:
        return int(valeur) if valeur else None
    except ValueError:
        return None


def url(filtres: Filtres, annee=None, mois=None, jour=None, page=None) -> str:
    """Adresse d'une page de la galerie, filtres compris."""
    params: dict = {}
    for cle, valeur in (("annee", annee), ("mois", mois), ("jour", jour)):
        if valeur is not None:
            params[cle] = valeur
    if filtres.du:
        params["du"] = filtres.du.isoformat()
    if filtres.au:
        params["au"] = filtres.au.isoformat()
    if filtres.type:
        params["type"] = filtres.type
    if filtres.origine:
        params["origine"] = filtres.origine
    if page and page > 1:
        params["page"] = page
    return "/" + ("?" + urlencode(params) if params else "")


def libelle_annee(annee) -> str:
    return "Sans date" if annee == SANS else str(annee)


def libelle_mois(mois) -> str:
    return "Mois inconnu" if mois == SANS else MOIS[mois - 1].capitalize()


def libelle_jour(annee, mois, jour) -> str:
    if jour == SANS:
        return "Jour inconnu"
    try:
        return f"{JOURS[date(annee, mois, jour).weekday()]} {jour}"
    except ValueError:
        return str(jour)       # « 30 février » : on garde le numéro


def construire_vue(index: Index, filtres: Filtres, annee=None, mois=None,
                   jour=None, page: int = 1, message: str | None = None) -> VueGalerie:
    fil = [("Toutes les années", url(filtres))]

    if annee is None:                                   # accueil : les années
        blocs = [(libelle_annee(a), url(filtres, annee=a), n)
                 for a, n in index.compter_annees(filtres)]
        return VueGalerie("Galerie", fil, filtres, blocs,
                          total=sum(n for _, _, n in blocs), message=message)

    fil.append((libelle_annee(annee), url(filtres, annee=annee)))
    if annee != SANS and mois is None:                  # une année : ses mois
        blocs = [(libelle_mois(m), url(filtres, annee=annee, mois=m), n)
                 for m, n in index.compter_mois(filtres, annee)]
        return VueGalerie(libelle_annee(annee), fil, filtres, blocs,
                          total=sum(n for _, _, n in blocs), message=message)

    blocs: list[tuple[str, str, int]] = []
    par_jour = annee != SANS and mois != SANS
    if annee == SANS:
        mois = jour = None                              # le rayon n'a pas de sous-niveau
    elif mois == SANS:
        fil.append(("Mois inconnu", url(filtres, annee=annee, mois=SANS)))
        jour = None
    else:
        fil.append((libelle_mois(mois), url(filtres, annee=annee, mois=mois)))
        jours = index.compter_jours(filtres, annee, mois)
        # Le niveau « jours » n'existe que si au moins un jour est connu (spec §5).
        if any(j != SANS for j, _ in jours):
            blocs = [(libelle_jour(annee, mois, j), url(filtres, annee, mois, j), n)
                     for j, n in jours]
        if jour is not None:
            fil.append((libelle_jour(annee, mois, jour), url(filtres, annee, mois, jour)))

    medias = index.selectionner(filtres, annee, mois, jour)
    total = len(medias)
    pages = max(1, ceil(total / TAILLE_PAGE))
    page = min(max(1, page), pages)
    tranche = medias[(page - 1) * TAILLE_PAGE: page * TAILLE_PAGE]

    groupes: list[tuple[str, list[Media]]] = []
    if par_jour and blocs:
        for m in tranche:
            titre = libelle_jour(annee, mois, m.c.jour if m.c.jour is not None else SANS)
            if not groupes or groupes[-1][0] != titre:
                groupes.append((titre, []))
            groupes[-1][1].append(m)
    elif tranche:
        groupes = [("", tranche)]

    return VueGalerie(
        fil[-1][0], fil, filtres, blocs, groupes, page, pages, total,
        precedente=url(filtres, annee, mois, jour, page - 1) if page > 1 else None,
        suivante=url(filtres, annee, mois, jour, page + 1) if page < pages else None,
        message=message)
```

- [ ] **Étape 4 : lancer les tests pour les voir passer**

Lancer : `python3 -m pytest tests/test_galerie_vue.py -q`
Attendu : `11 passed`

- [ ] **Étape 5 : valider par mutation**

- supprimer la garde `if any(j != SANS …)` → `test_un_mois_sans_aucun_jour_connu…` tombe ;
- dans `url`, ne plus recopier `filtres.type` → `test_la_pagination_garde_les_filtres` tombe ;
- retirer `page = min(max(1, page), pages)` → `test_une_page_hors_limites…` tombe.

- [ ] **Étape 6 : commit**

```bash
git add phototheque/galerie_vue.py tests/test_galerie_vue.py
git commit -F - <<'FIN'
feat(galerie): modele de page, niveaux annee/mois/jour et pagination (#31)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Tâche 4 : la table des vignettes et ses fichiers

**Fichiers :**
- Créer : `phototheque/vignettes.py`
- Modifier : `phototheque/config.py` (ajouter deux variables après `JOURNAL_DB`)
- Test : `tests/test_vignettes.py`

**Interfaces :**
- Produit :
  - `config.GALERIE_DB: Path` (défaut `~/phototheque_galerie.db`), `config.VIGNETTES_DIR: Path` (défaut `DATA_DIR / "vignettes"`) ;
  - `vignettes.EMPREINTE` (regex, 64 hexadécimaux minuscules) ;
  - `chemin_vignette(dossier: Path, empreinte: str) -> Path`, `chemin_moyenne(dossier: Path, empreinte: str) -> Path` ;
  - `Vignettes(db_path)` : `traitees() -> set[str]`, `enregistrer_faite(empreinte, largeur, hauteur, methode)`, `enregistrer_erreur(empreinte, erreur)`, `oublier_erreurs() -> int`, `bilan() -> dict` (`faites`, `erreurs`, `derniere`), `dernieres_erreurs(n=20) -> list[dict]`, `close()`.

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
"""Tests de la table des vignettes (base à part, reprenable)."""
from pathlib import Path

import pytest

from phototheque import vignettes as v

E1, E2 = "a" * 64, "b" * 64


def test_une_vignette_faite_est_retenue_apres_reouverture(tmp_path):
    base = v.Vignettes(tmp_path / "g.db")
    base.enregistrer_faite(E1, 400, 300, "photo")
    base.close()
    assert v.Vignettes(tmp_path / "g.db").traitees() == {E1}


def test_une_erreur_compte_comme_traitee_et_laisse_une_trace(tmp_path):
    base = v.Vignettes(tmp_path / "g.db")
    base.enregistrer_erreur(E2, "ffmpeg : Invalid data found")
    assert base.traitees() == {E2}
    assert base.dernieres_erreurs()[0]["erreur"] == "ffmpeg : Invalid data found"


def test_reussir_apres_une_erreur_efface_l_erreur(tmp_path):
    base = v.Vignettes(tmp_path / "g.db")
    base.enregistrer_erreur(E1, "x")
    base.enregistrer_faite(E1, 160, 120, "exif")
    b = base.bilan()
    assert (b["faites"], b["erreurs"]) == (1, 0)


def test_oublier_les_erreurs_les_remet_en_file(tmp_path):
    base = v.Vignettes(tmp_path / "g.db")
    base.enregistrer_faite(E1, 1, 1, "photo")
    base.enregistrer_erreur(E2, "x")
    assert base.oublier_erreurs() == 1
    assert base.traitees() == {E1}


def test_bilan_d_une_base_vide(tmp_path):
    assert v.Vignettes(tmp_path / "g.db").bilan() == {"faites": 0, "erreurs": 0, "derniere": None}


def test_chemins_des_fichiers_repartis_par_deux_premiers_caracteres(tmp_path):
    assert v.chemin_vignette(tmp_path, E1) == tmp_path / "aa" / f"{E1}.webp"
    assert v.chemin_moyenne(tmp_path, E1) == tmp_path / "moyennes" / "aa" / f"{E1}.webp"


@pytest.mark.parametrize("forgee", ["../../etc/passwd", "A" * 64, "a" * 63, "g" * 64, "",
                                    "a" * 64 + "/../x"])
def test_une_empreinte_forgee_ne_passe_pas_le_motif(forgee):
    assert not v.EMPREINTE.fullmatch(forgee)


def test_les_chemins_refusent_une_empreinte_forgee(tmp_path):
    with pytest.raises(ValueError):
        v.chemin_vignette(tmp_path, "../" + "a" * 61)
```

- [ ] **Étape 2 : lancer les tests pour les voir échouer**

Lancer : `python3 -m pytest tests/test_vignettes.py -q`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'phototheque.vignettes'`

- [ ] **Étape 3 : écrire le module et la configuration**

Dans `phototheque/config.py`, juste après la ligne `JOURNAL_DB = …` :

```python
# Galerie (issue #31) : base à part, pour la même raison que le journal — le
# catalogue appartient au trieur. Elle ne dit que quelles vignettes sont
# faites ou en échec ; les vignettes elles-mêmes sont des fichiers WebP sur le
# disque système (jamais sur Famille : c'est le disque lent des médias).
GALERIE_DB: Path = Path(os.environ.get("GALERIE_DB", str(Path.home() / "phototheque_galerie.db")))
```

Et, après la ligne `APK_FILE = …` (qui suit `DATA_DIR`) :

```python
VIGNETTES_DIR: Path = Path(os.environ.get("VIGNETTES_DIR", str(DATA_DIR / "vignettes")))
```

`phototheque/vignettes.py` :

```python
"""Table des vignettes de la galerie : ce qui est fait, ce qui a échoué.

C'est elle qui rend le recensement REPRENABLE : une vignette faite ou en
échec n'est plus retentée (sauf `oublier_erreurs`, à la demande). Base
distincte du catalogue (`config.GALERIE_DB`), en mode WAL : le serveur web la
lit pendant que le recensement, un autre processus, y écrit.
"""

import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

# Une empreinte SHA-256 en hexadécimal minuscule, et rien d'autre. C'est le
# seul identifiant qu'une requête de la galerie peut porter (spec §7).
EMPREINTE = re.compile(r"[0-9a-f]{64}")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vignettes (
  empreinte TEXT PRIMARY KEY,
  etat TEXT NOT NULL,              -- 'faite' ou 'erreur'
  largeur INTEGER, hauteur INTEGER,
  methode TEXT,                    -- 'exif', 'photo' ou 'video'
  erreur TEXT,
  faite_le TEXT NOT NULL);
"""


def _verifier(empreinte: str) -> str:
    if not EMPREINTE.fullmatch(empreinte):
        raise ValueError(f"empreinte non autorisée : {empreinte!r}")
    return empreinte


def chemin_vignette(dossier: Path, empreinte: str) -> Path:
    """`<dossier>/aa/aaaa….webp` : 256 sous-dossiers plutôt que 45 000
    fichiers dans un seul répertoire."""
    e = _verifier(empreinte)
    return dossier / e[:2] / f"{e}.webp"


def chemin_moyenne(dossier: Path, empreinte: str) -> Path:
    """La taille intermédiaire (1280 px), fabriquée à la première ouverture."""
    e = _verifier(empreinte)
    return dossier / "moyennes" / e[:2] / f"{e}.webp"


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Vignettes:
    def __init__(self, db_path) -> None:
        self._cx = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
        self._lock = threading.Lock()
        with self._lock:
            self._cx.execute("PRAGMA journal_mode=WAL")
            self._cx.executescript(_SCHEMA)
            self._cx.commit()

    def traitees(self) -> set[str]:
        with self._lock:
            return {r[0] for r in self._cx.execute("SELECT empreinte FROM vignettes")}

    def enregistrer_faite(self, empreinte: str, largeur: int, hauteur: int, methode: str) -> None:
        with self._lock:
            self._cx.execute(
                "INSERT OR REPLACE INTO vignettes VALUES (?, 'faite', ?, ?, ?, NULL, ?)",
                (empreinte, largeur, hauteur, methode, _maintenant()))
            self._cx.commit()

    def enregistrer_erreur(self, empreinte: str, erreur: str) -> None:
        with self._lock:
            self._cx.execute(
                "INSERT OR REPLACE INTO vignettes VALUES (?, 'erreur', NULL, NULL, NULL, ?, ?)",
                (empreinte, erreur[:500], _maintenant()))
            self._cx.commit()

    def oublier_erreurs(self) -> int:
        with self._lock:
            n = self._cx.execute("DELETE FROM vignettes WHERE etat='erreur'").rowcount
            self._cx.commit()
            return n

    def bilan(self) -> dict:
        with self._lock:
            faites, erreurs, derniere = self._cx.execute(
                "SELECT COALESCE(SUM(etat='faite'), 0), COALESCE(SUM(etat='erreur'), 0),"
                " MAX(faite_le) FROM vignettes").fetchone()
        return {"faites": faites, "erreurs": erreurs, "derniere": derniere}

    def dernieres_erreurs(self, n: int = 20) -> list[dict]:
        with self._lock:
            lignes = self._cx.execute(
                "SELECT empreinte, erreur, faite_le FROM vignettes WHERE etat='erreur'"
                " ORDER BY faite_le DESC LIMIT ?", (n,)).fetchall()
        return [{"empreinte": e, "erreur": err, "quand": q} for e, err, q in lignes]

    def close(self) -> None:
        with self._lock:
            self._cx.close()
```

- [ ] **Étape 4 : lancer les tests pour les voir passer**

Lancer : `python3 -m pytest tests/test_vignettes.py -q`
Attendu : `13 passed`

- [ ] **Étape 5 : valider par mutation**

- remplacer `fullmatch` par `match` dans le test paramétré et dans `_verifier` → le cas `"a" * 64 + "/../x"` doit tomber (un préfixe valide ne suffit pas) ;
- `enregistrer_faite` en `INSERT OR IGNORE` → `test_reussir_apres_une_erreur…` tombe.

- [ ] **Étape 6 : commit**

```bash
git add phototheque/config.py phototheque/vignettes.py tests/test_vignettes.py
git commit -F - <<'FIN'
feat(galerie): table des vignettes reprenable et chemins des fichiers (#31)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Tâche 5 : fabriquer une vignette avec exiftool et ffmpeg

**Fichiers :**
- Créer : `phototheque/fabrique.py`
- Test : `tests/test_fabrique.py`

**Interfaces :**
- Produit :
  - `TAILLE_VIGNETTE = 400`, `TAILLE_MOYENNE = 1280` ;
  - `class ErreurVignette(Exception)` ;
  - `filtre(orientation: int | None, taille: int) -> str` ;
  - `lire_metadonnees(chemins: list[str], executer=subprocess.run) -> dict[str, dict]` (clé : le chemin tel que donné) ;
  - `fabriquer_vignette(chemin: str, type_: str, meta: dict, cible: Path, executer=subprocess.run) -> tuple[int, int, str]` → `(largeur, hauteur, methode)` ;
  - `fabriquer_moyenne(chemin: str, orientation: int | None, cible: Path, executer=subprocess.run) -> None`.

Pourquoi `executer` : les tests unitaires remplacent `subprocess.run` pour
vérifier les commandes sans outils ; des tests d'intégration, sautés si
`ffmpeg` manque, les exécutent pour de vrai. **`exiftool` n'est pas installé
sur le poste de développement** : ce qui en dépend se vérifie sur le NUC
(tâche 9).

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
"""Tests de la fabrique de vignettes (commandes, puis vrais outils si présents)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from phototheque import fabrique as f

AVEC_FFMPEG = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None
    or b"libwebp" not in subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                                         capture_output=True).stdout,
    reason="ffmpeg avec libwebp absent")


class Enregistreur:
    """Remplace subprocess.run : note les commandes, rend une réponse choisie."""
    def __init__(self, reponses=None):
        self.commandes = []
        self.reponses = reponses or {}

    def __call__(self, cmd, **kw):
        self.commandes.append(cmd)
        outil = Path(cmd[0]).name
        if outil == "ffmpeg":
            Path(cmd[-1]).write_bytes(b"RIFF....WEBP")      # le fichier de sortie
        sortie = self.reponses.get(outil, b"")
        return subprocess.CompletedProcess(cmd, 0, stdout=sortie, stderr=b"")


@pytest.mark.parametrize("orientation,attendu", [
    (None, ""), (1, ""), (3, "hflip,vflip"), (6, "transpose=1"), (8, "transpose=2")])
def test_filtre_applique_l_orientation_puis_reduit_sans_agrandir(orientation, attendu):
    vf = f.filtre(orientation, 400)
    assert vf.endswith("scale='min(400,iw)':'min(400,ih)':force_original_aspect_ratio=decrease")
    assert vf.startswith(attendu)


def test_lire_metadonnees_par_lot_et_indexe_par_chemin():
    rep = json.dumps([{"SourceFile": "/b/a.jpg", "DateTimeOriginal": "2019:05:04 10:00:00",
                       "Orientation": 6, "ThumbnailLength": 14000}]).encode()
    ex = Enregistreur({"exiftool": rep})
    meta = f.lire_metadonnees(["/b/a.jpg"], executer=ex)
    assert meta["/b/a.jpg"]["Orientation"] == 6
    cmd = ex.commandes[0]
    assert cmd[0] == "exiftool" and "-json" in cmd and "-n" in cmd


def test_photo_avec_vignette_exif_ne_lit_que_l_en_tete(tmp_path):
    ex = Enregistreur({"exiftool": b"\xff\xd8jpeg", "ffprobe": b"160,120\n"})
    l, h, methode = f.fabriquer_vignette("/b/a.jpg", "photo",
                                         {"ThumbnailLength": 14000, "Orientation": 6},
                                         tmp_path / "v.webp", executer=ex)
    assert (l, h, methode) == (160, 120, "exif")
    assert ex.commandes[0][:3] == ["exiftool", "-b", "-ThumbnailImage"]
    ffmpeg = next(c for c in ex.commandes if c[0] == "ffmpeg")
    assert "-noautorotate" in ffmpeg, "la rotation est la nôtre, pas celle de ffmpeg"
    assert "transpose=1" in ffmpeg[ffmpeg.index("-vf") + 1]
    assert (tmp_path / "v.webp").exists()


def test_photo_sans_vignette_exif_passe_par_ffmpeg(tmp_path):
    ex = Enregistreur({"ffprobe": b"400,300\n"})
    *_, methode = f.fabriquer_vignette("/b/a.jpg", "photo", {}, tmp_path / "v.webp", executer=ex)
    assert methode == "photo"
    assert not any(c[0] == "exiftool" for c in ex.commandes)


def test_video_ne_lit_que_le_debut(tmp_path):
    ex = Enregistreur({"ffprobe": b"400,225\n"})
    *_, methode = f.fabriquer_vignette("/b/v.mp4", "video", {}, tmp_path / "v.webp", executer=ex)
    ffmpeg = next(c for c in ex.commandes if c[0] == "ffmpeg")
    assert methode == "video"
    assert ffmpeg.index("-ss") < ffmpeg.index("-i"), "-ss AVANT -i : saut sans décoder"


def test_une_sortie_ffmpeg_vide_est_une_erreur(tmp_path):
    def ex(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Invalid data found")
    with pytest.raises(f.ErreurVignette, match="Invalid data"):
        f.fabriquer_vignette("/b/a.jpg", "photo", {}, tmp_path / "v.webp", executer=ex)
    assert not (tmp_path / "v.webp").exists(), "jamais de vignette à moitié écrite"


@AVEC_FFMPEG
def test_vraie_photo_reduite_a_400(tmp_path):
    src = tmp_path / "grande.jpg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=800x600", "-frames:v", "1", str(src)], check=True)
    assert f.fabriquer_vignette(str(src), "photo", {}, tmp_path / "v.webp")[:2] == (400, 300)


@AVEC_FFMPEG
def test_vraie_petite_photo_jamais_agrandie(tmp_path):
    src = tmp_path / "petite.jpg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=100x80", "-frames:v", "1", str(src)], check=True)
    assert f.fabriquer_vignette(str(src), "photo", {}, tmp_path / "v.webp")[:2] == (100, 80)


@AVEC_FFMPEG
def test_vraie_video_courte(tmp_path):
    # Moins d'une seconde : le saut à 1 s ne donne rien, on retente à 0.
    src = tmp_path / "courte.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=640x360:duration=0.5", "-pix_fmt", "yuv420p", str(src)],
                   check=True)
    assert f.fabriquer_vignette(str(src), "video", {}, tmp_path / "v.webp")[2] == "video"


@AVEC_FFMPEG
def test_vrai_fichier_corrompu(tmp_path):
    src = tmp_path / "casse.jpg"
    src.write_bytes(b"pas une image")
    with pytest.raises(f.ErreurVignette):
        f.fabriquer_vignette(str(src), "photo", {}, tmp_path / "v.webp")
```

- [ ] **Étape 2 : lancer les tests pour les voir échouer**

Lancer : `python3 -m pytest tests/test_fabrique.py -q`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'phototheque.fabrique'`

- [ ] **Étape 3 : écrire le module**

```python
"""Fabrique des vignettes : exiftool et ffmpeg, rien d'autre (spec §3).

Le coût, c'est d'OUVRIR le fichier sur un disque NTFS à ~7 Mo/s, pas de le
traiter. D'où trois chemins, du moins cher au plus cher :

- photo avec vignette EXIF (73 % des JPEG, mesuré) : `exiftool` n'en lit que
  l'en-tête. Cette vignette fait ~160 px ; elle est gardée à sa taille, jamais
  agrandie (elle deviendrait floue) ;
- photo sans vignette EXIF : `ffmpeg` décode le fichier entier ;
- vidéo : `ffmpeg -ss 1 -i …` saute à la première seconde SANS décoder ce qui
  précède, et ne lit donc que le début du fichier.

L'orientation EXIF (photo prise en portrait) est appliquée par nous, à partir
de la balise lue par exiftool, et `-noautorotate` empêche ffmpeg de la
réappliquer une seconde fois. Les vidéos, elles, gardent la rotation
automatique de ffmpeg (métadonnée de conteneur, pas EXIF).
"""

import json
import subprocess
from pathlib import Path

TAILLE_VIGNETTE = 400
TAILLE_MOYENNE = 1280

# Balises lues en un seul appel par lot. `-n` rend Orientation et
# ThumbnailLength numériques ; les dates restent du texte « AAAA:MM:JJ hh:mm:ss ».
_BALISES = ["DateTimeOriginal", "CreateDate", "CreationDate", "MediaCreateDate",
            "Orientation", "ThumbnailLength"]

# Orientation EXIF → filtre ffmpeg (1 = rien à faire).
_ROTATIONS = {2: "hflip", 3: "hflip,vflip", 4: "vflip", 5: "transpose=0",
              6: "transpose=1", 7: "transpose=3", 8: "transpose=2"}


class ErreurVignette(Exception):
    """La vignette n'a pas pu être faite ; le message dit pourquoi."""


def filtre(orientation: int | None, taille: int) -> str:
    """Chaîne `-vf` : redresser, puis réduire à `taille` sans jamais agrandir."""
    etapes = []
    if orientation in _ROTATIONS:
        etapes.append(_ROTATIONS[orientation])
    etapes.append(f"scale='min({taille},iw)':'min({taille},ih)'"
                  ":force_original_aspect_ratio=decrease")
    return ",".join(etapes)


def lire_metadonnees(chemins: list[str], executer=subprocess.run) -> dict[str, dict]:
    """Balises utiles de tout un lot, en UN appel exiftool (liste sur l'entrée
    standard : pas de limite de longueur de ligne de commande)."""
    if not chemins:
        return {}
    cmd = ["exiftool", "-json", "-n", "-api", "QuickTimeUTC=1",
           *[f"-{b}" for b in _BALISES], "-@", "-"]
    r = executer(cmd, input="\n".join(chemins).encode(), capture_output=True, timeout=600)
    try:
        lignes = json.loads(r.stdout or b"[]")
    except json.JSONDecodeError:
        return {}
    return {d.get("SourceFile"): d for d in lignes if isinstance(d, dict)}


def _dimensions(fichier: Path, executer) -> tuple[int, int]:
    r = executer(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "stream=width,height", "-of", "csv=p=0", str(fichier)],
                 capture_output=True, timeout=60)
    try:
        largeur, hauteur = (int(x) for x in r.stdout.decode().strip().split(",")[:2])
    except ValueError as e:
        raise ErreurVignette(f"dimensions illisibles : {r.stdout!r}") from e
    return largeur, hauteur


def _ffmpeg(avant_entree: list[str], entree: str, vf: str, cible: Path,
            executer, donnees: bytes | None = None) -> bool:
    """Une image WebP dans `cible`, écrite à côté puis renommée (jamais de
    fichier à moitié écrit). Faux si ffmpeg n'a rien produit."""
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = cible.with_name(cible.name + ".partiel")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *avant_entree,
           "-i", entree, "-frames:v", "1", "-vf", vf,
           "-c:v", "libwebp", "-quality", "75", "-f", "webp", str(partiel)]
    r = executer(cmd, input=donnees, capture_output=True, timeout=300)
    if r.returncode != 0 or not partiel.exists() or partiel.stat().st_size == 0:
        partiel.unlink(missing_ok=True)
        _ffmpeg.derniere_erreur = (r.stderr or b"").decode(errors="replace")[-300:]
        return False
    partiel.replace(cible)
    return True


_ffmpeg.derniere_erreur = ""


def fabriquer_vignette(chemin: str, type_: str, meta: dict, cible: Path,
                       executer=subprocess.run) -> tuple[int, int, str]:
    """Écrit la vignette de `chemin` dans `cible` ; renvoie (largeur, hauteur, méthode)."""
    orientation = meta.get("Orientation")
    if type_ == "video":
        vf = filtre(None, TAILLE_VIGNETTE)
        if not (_ffmpeg(["-ss", "1"], chemin, vf, cible, executer)
                or _ffmpeg(["-ss", "0"], chemin, vf, cible, executer)):
            raise ErreurVignette(f"ffmpeg (vidéo) : {_ffmpeg.derniere_erreur}")
        return (*_dimensions(cible, executer), "video")

    vf = filtre(orientation, TAILLE_VIGNETTE)
    if meta.get("ThumbnailLength"):
        r = executer(["exiftool", "-b", "-ThumbnailImage", chemin],
                     capture_output=True, timeout=60)
        if r.stdout and _ffmpeg(["-noautorotate", "-f", "jpeg_pipe"], "-", vf, cible,
                                executer, donnees=r.stdout):
            return (*_dimensions(cible, executer), "exif")
    if not _ffmpeg(["-noautorotate"], chemin, vf, cible, executer):
        raise ErreurVignette(f"ffmpeg (photo) : {_ffmpeg.derniere_erreur}")
    return (*_dimensions(cible, executer), "photo")


def fabriquer_moyenne(chemin: str, orientation: int | None, cible: Path,
                      executer=subprocess.run) -> None:
    """Taille intermédiaire (1280 px) d'une photo, pour l'affichage en grand."""
    if not _ffmpeg(["-noautorotate"], chemin, filtre(orientation, TAILLE_MOYENNE),
                   cible, executer):
        raise ErreurVignette(f"ffmpeg (moyenne) : {_ffmpeg.derniere_erreur}")
```

- [ ] **Étape 4 : lancer les tests pour les voir passer**

Lancer : `python3 -m pytest tests/test_fabrique.py -q`
Attendu : `14 passed` sur le poste (ffmpeg avec libwebp y est), dont les quatre tests `vrai…`.

- [ ] **Étape 5 : valider par mutation**

- retirer `"-noautorotate"` du chemin EXIF → `test_photo_avec_vignette_exif…` tombe ;
- placer `-ss` après `-i` → `test_video_ne_lit_que_le_debut` tombe ;
- retirer le repli `-ss 0` → `test_vraie_video_courte` tombe ;
- retirer `min(…,iw)` du filtre → `test_vraie_petite_photo_jamais_agrandie` tombe.

- [ ] **Étape 6 : commit**

```bash
git add phototheque/fabrique.py tests/test_fabrique.py
git commit -F - <<'FIN'
feat(galerie): fabrique de vignettes par exiftool et ffmpeg (#31)

Vignette EXIF quand elle existe (en-tete seul), ffmpeg sinon, debut de
fichier seulement pour la video. Orientation EXIF appliquee par nous,
jamais d'agrandissement, jamais de fichier a moitie ecrit.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Tâche 6 : le recensement, reprenable et discret

**Fichiers :**
- Créer : `phototheque/recensement.py`
- Test : `tests/test_recensement.py`

**Interfaces :**
- Consomme : `galerie_index.Index.depuis_catalogue`, `Media` ; `vignettes.Vignettes`, `chemin_vignette` ; `fabrique.lire_metadonnees`, `fabrique.fabriquer_vignette`, `ErreurVignette` ; `sessions.identifiant_valide(nom) -> bool`, `sessions._mtime_le_plus_recent(dossier) -> float` ; `mediasort.dates._pick_metadata_date(tags) -> date | None`, `mediasort.dates.date_from_filename(nom) -> date | None`
- Produit :
  - `LOT = 50` ;
  - `a_traiter(catalog_db, vignettes, bibliotheque) -> list[Media]` (le plus récent d'abord) ;
  - `synchro_en_cours(incoming: Path, fenetre_s=300, maintenant=time.time) -> bool` ;
  - `recolter_date(meta: dict, nom: str) -> tuple[str, str] | None` → `("AAAA-MM-JJ", "metadata"|"filename")` ;
  - `ecrire_dates(catalog_db, dates: list[tuple[str, str, str]]) -> int` ;
  - `class Passe` : `Passe(catalog_db, vignettes, dossier, bibliotheque, incoming, lire=…, fabriquer=…, dormir=time.sleep, doit_s_arreter=lambda: False)`, `.executer(limite=None) -> dict` (`faites`, `erreurs`, `dates`) ;
  - `main(argv=None) -> int` (point d'entrée `python3 -m phototheque.recensement`).

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
"""Tests du recensement : reprise, erreurs isolées, dates, pause, verrou."""
import os
import sqlite3
import time
from pathlib import Path

from mediasort.catalog import Catalog
from phototheque import recensement as r
from phototheque.fabrique import ErreurVignette
from phototheque.vignettes import Vignettes, chemin_vignette


def _bib(tmp_path, fichiers):
    """Crée des fichiers sous une bibliothèque et les inscrit au catalogue."""
    bib = tmp_path / "Famille"
    cat = Catalog(tmp_path / "cat.db")
    empreintes = []
    for i, (rel, date_prise) in enumerate(fichiers):
        p = bib / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        e = f"{i:064x}"
        cat.add_media(e, 1, str(p), date_prise, "seed" if date_prise is None else "metadata")
        empreintes.append(e)
    cat.close()
    return bib, tmp_path / "cat.db", empreintes


def _faux_fabriquer(echecs=()):
    def fabriquer(chemin, type_, meta, cible, executer=None):
        if Path(chemin).name in echecs:
            raise ErreurVignette("ffmpeg (photo) : Invalid data found")
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(b"webp")
        return 400, 300, "photo"
    return fabriquer


def _passe(tmp_path, bib, db, **kw):
    kw.setdefault("lire", lambda chemins: {})
    kw.setdefault("fabriquer", _faux_fabriquer())
    return r.Passe(db, Vignettes(tmp_path / "g.db"), tmp_path / "vign", bib,
                   tmp_path / "incoming", dormir=lambda s: None, **kw)


def _date_prise(db, e):
    cx = sqlite3.connect(db)
    try:
        return cx.execute("SELECT date_prise, source_date FROM medias WHERE empreinte=?",
                          (e,)).fetchone()
    finally:
        cx.close()


def test_la_passe_fait_les_vignettes(tmp_path):
    bib, db, (e,) = _bib(tmp_path, [("Photos/2023/06 JUIN/IMG_1.jpg", None)])
    assert _passe(tmp_path, bib, db).executer()["faites"] == 1
    assert chemin_vignette(tmp_path / "vign", e).exists()


def test_le_recensement_reprend_ou_il_s_est_arrete(tmp_path):
    bib, db, _ = _bib(tmp_path, [(f"Photos/2023/06 JUIN/IMG_{i}.jpg", None) for i in range(5)])
    assert _passe(tmp_path, bib, db).executer(limite=2)["faites"] == 2
    vus = []
    def fabriquer(chemin, type_, meta, cible, executer=None):
        vus.append(chemin)
        return _faux_fabriquer()(chemin, type_, meta, cible)
    assert _passe(tmp_path, bib, db, fabriquer=fabriquer).executer()["faites"] == 3
    assert len(vus) == 3, "les deux premières ne sont pas refaites"


def test_une_vignette_en_echec_n_arrete_pas_la_passe(tmp_path):
    bib, db, (e1, e2) = _bib(tmp_path, [("Photos/2023/06 JUIN/casse.jpg", None),
                                        ("Photos/2023/06 JUIN/bon.jpg", None)])
    bilan = _passe(tmp_path, bib, db, fabriquer=_faux_fabriquer({"casse.jpg"})).executer()
    assert (bilan["faites"], bilan["erreurs"]) == (1, 1)
    trace = Vignettes(tmp_path / "g.db").dernieres_erreurs()
    assert trace[0]["empreinte"] == e1 and "Invalid data" in trace[0]["erreur"]


def test_un_fichier_disparu_est_note_et_la_passe_continue(tmp_path):
    # Point de vigilance n° 2 : un dossier curaté déplacé à la main.
    bib, db, (e1, _) = _bib(tmp_path, [("Photos/2023/06 JUIN/parti.jpg", None),
                                       ("Photos/2023/06 JUIN/la.jpg", None)])
    (bib / "Photos/2023/06 JUIN/parti.jpg").unlink()
    bilan = _passe(tmp_path, bib, db).executer()
    assert (bilan["faites"], bilan["erreurs"]) == (1, 1)
    assert "absent" in Vignettes(tmp_path / "g.db").dernieres_erreurs()[0]["erreur"]


def test_les_plus_recents_d_abord(tmp_path):
    bib, db, _ = _bib(tmp_path, [("Photos/2013/05 MAI/vieux.jpg", None),
                                 ("Photos/2023/06 JUIN/recent.jpg", None)])
    ordre = [m.nom for m in r.a_traiter(db, Vignettes(tmp_path / "g.db"), bib)]
    assert ordre == ["recent.jpg", "vieux.jpg"]


def test_la_recolte_ecrit_date_prise_depuis_les_metadonnees(tmp_path):
    bib, db, (e,) = _bib(tmp_path, [("Photos/2019/05 MAI/IMG_1.jpg", None)])
    chemin = str(bib / "Photos/2019/05 MAI/IMG_1.jpg")
    lire = lambda chemins: {chemin: {"DateTimeOriginal": "2019:05:04 10:00:00"}}
    assert _passe(tmp_path, bib, db, lire=lire).executer()["dates"] == 1
    assert _date_prise(db, e) == ("2019-05-04", "metadata")


def test_la_recolte_retombe_sur_le_nom_du_fichier(tmp_path):
    bib, db, (e,) = _bib(tmp_path, [("WhatsApp/Photos/2023/06 JUIN/IMG-20230625-WA0025.jpg", None)])
    _passe(tmp_path, bib, db).executer()
    assert _date_prise(db, e) == ("2023-06-25", "filename")


def test_une_date_nulle_ne_s_ecrit_pas(tmp_path):
    # Point de vigilance n° 3 : « 0000:00:00 » des vieux appareils.
    bib, db, (e,) = _bib(tmp_path, [("Photos/Divers/AK 2.jpg", None)])
    chemin = str(bib / "Photos/Divers/AK 2.jpg")
    lire = lambda chemins: {chemin: {"DateTimeOriginal": "0000:00:00 00:00:00"}}
    _passe(tmp_path, bib, db, lire=lire).executer()
    assert _date_prise(db, e) == (None, "seed")


def test_la_recolte_n_ecrase_jamais_une_date_connue(tmp_path):
    bib, db, (e,) = _bib(tmp_path, [("Photos/2019/05 MAI/IMG_1.jpg", "2019-05-01")])
    chemin = str(bib / "Photos/2019/05 MAI/IMG_1.jpg")
    lire = lambda chemins: {chemin: {"DateTimeOriginal": "2019:05:04 10:00:00"}}
    _passe(tmp_path, bib, db, lire=lire).executer()
    assert _date_prise(db, e) == ("2019-05-01", "metadata")


def test_ecrire_dates_ne_touche_que_les_trous(tmp_path):
    bib, db, (e1, e2) = _bib(tmp_path, [("Photos/a.jpg", None), ("Photos/b.jpg", "2001-01-01")])
    n = r.ecrire_dates(db, [(e1, "2020-02-02", "metadata"), (e2, "2020-02-02", "metadata")])
    assert n == 1 and _date_prise(db, e2) == ("2001-01-01", "metadata")


def test_synchro_en_cours_voit_une_session_recente(tmp_path):
    incoming = tmp_path / "incoming"
    session = incoming / ("c" * 32)
    session.mkdir(parents=True)
    (session / "a.jpg.partiel").write_bytes(b"x")
    assert r.synchro_en_cours(incoming)
    assert not r.synchro_en_cours(incoming, maintenant=lambda: time.time() + 3600)


def test_synchro_en_cours_ignore_la_quarantaine(tmp_path):
    incoming = tmp_path / "incoming"
    (incoming / "_echecs" / "x").mkdir(parents=True)
    assert not r.synchro_en_cours(incoming)


def test_la_passe_attend_la_fin_d_une_synchro(tmp_path, monkeypatch):
    bib, db, _ = _bib(tmp_path, [("Photos/2023/06 JUIN/IMG_1.jpg", None)])
    reponses = iter([True, True, False])
    monkeypatch.setattr(r, "synchro_en_cours", lambda *a, **k: next(reponses))
    siestes = []
    p = r.Passe(db, Vignettes(tmp_path / "g.db"), tmp_path / "vign", bib, tmp_path / "in",
                lire=lambda c: {}, fabriquer=_faux_fabriquer(), dormir=siestes.append)
    assert p.executer()["faites"] == 1
    assert len(siestes) == 2


def test_un_arret_demande_sort_proprement(tmp_path):
    bib, db, _ = _bib(tmp_path, [(f"Photos/2023/06 JUIN/{i}.jpg", None) for i in range(3)])
    p = _passe(tmp_path, bib, db, doit_s_arreter=lambda: True)
    assert p.executer()["faites"] == 0


def test_un_seul_recensement_a_la_fois(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib
    import phototheque.config as c
    importlib.reload(c)
    verrou = r._prendre_verrou(tmp_path / "recensement.verrou")
    assert verrou is not None
    assert r._prendre_verrou(tmp_path / "recensement.verrou") is None
    verrou.close()
```

- [ ] **Étape 2 : lancer les tests pour les voir échouer**

Lancer : `python3 -m pytest tests/test_recensement.py -q`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'phototheque.recensement'`

- [ ] **Étape 3 : écrire le module**

```python
"""Le grand recensement de la galerie (spec §4) : vignettes + dates.

Une passe sur tout le catalogue qui, pour chaque média, fabrique sa vignette
et, si le catalogue ne connaît pas sa date de prise de vue, la récolte dans
les métadonnées (ou, à défaut, dans le nom du fichier). Les deux dans la même
passe : le coût est d'ouvrir le fichier, pas de le traiter.

Tourne dans son PROPRE processus (`phototheque-recensement.service`, `nice`
19, E/S au repos), jamais dans une requête web :
- reprenable : la table `vignettes` dit ce qui est fait ;
- discret : il s'efface quand une synchronisation du téléphone est en cours ;
- unique : un verrou de fichier empêche deux exemplaires ;
- permanent : l'arriéré fini, il repasse toutes les 10 minutes pour les
  médias nouvellement importés.

Écritures : fichiers de vignettes (disque système), base de la galerie, et
`date_prise` du catalogue SEULEMENT quand elle est vide. Rien sous la
bibliothèque.
"""

import argparse
import fcntl
import logging
import signal
import sqlite3
import time
from pathlib import Path

from mediasort.dates import _pick_metadata_date, date_from_filename

from . import config, fabrique, sessions
from .galerie_index import Index, Media
from .vignettes import Vignettes, chemin_vignette

LOT = 50                     # fichiers par appel exiftool et par écriture de dates
PAUSE_SYNCHRO_S = 30         # attente entre deux vérifications pendant une synchro
INTERVALLE_S = 600           # repos entre deux passes, une fois l'arriéré fini

_log = logging.getLogger("phototheque.recensement")


def a_traiter(catalog_db: Path, vignettes: Vignettes, bibliotheque: Path) -> list[Media]:
    """Médias sans vignette ni erreur, le plus récent d'abord : ce sont les
    mois qu'on regarde en premier qui se remplissent en premier."""
    faits = vignettes.traitees()
    restants = [m for m in Index.depuis_catalogue(catalog_db, bibliotheque).tous()
                if m.empreinte not in faits]
    restants.sort(key=lambda m: (m.c.annee or 0, m.c.mois or 0, m.c.jour or 0, m.nom),
                  reverse=True)
    return restants


def synchro_en_cours(incoming: Path, fenetre_s: int = 300, maintenant=time.time) -> bool:
    """Vrai si une session de synchronisation a été écrite récemment.

    Le recensement tourne dans un autre processus que le serveur : il ne voit
    pas ses verrous. Il regarde donc le disque, comme la purge des sessions
    abandonnées : un dossier au nom de session (32 hexadécimaux — ce qui
    écarte la quarantaine `_echecs`) modifié il y a moins de `fenetre_s`.
    """
    try:
        dossiers = list(incoming.iterdir())
    except FileNotFoundError:
        return False
    for d in dossiers:
        if d.is_dir() and sessions.identifiant_valide(d.name):
            if maintenant() - sessions._mtime_le_plus_recent(d) < fenetre_s:
                return True
    return False


def recolter_date(meta: dict, nom: str) -> tuple[str, str] | None:
    """La date de prise de vue d'un média, ou None. Jamais la date système du
    fichier : sur une bibliothèque copiée, elle ne dit que la date de la copie."""
    d = _pick_metadata_date(meta) if meta else None
    if d is not None and d.year >= 1900:
        return d.isoformat(), "metadata"
    d = date_from_filename(nom)
    if d is not None:
        return d.isoformat(), "filename"
    return None


def ecrire_dates(catalog_db: Path, dates: list[tuple[str, str, str]]) -> int:
    """Comble `date_prise` là où elle est vide, en une transaction courte (le
    trieur écrit dans le même fichier). Renvoie le nombre de lignes écrites."""
    if not dates:
        return 0
    cx = sqlite3.connect(str(catalog_db), timeout=30)
    try:
        with cx:
            n = 0
            for empreinte, jour, source in dates:
                n += cx.execute(
                    "UPDATE medias SET date_prise=?, source_date=?"
                    " WHERE empreinte=? AND date_prise IS NULL",
                    (jour, source, empreinte)).rowcount
        return n
    finally:
        cx.close()


class Passe:
    def __init__(self, catalog_db, vignettes: Vignettes, dossier: Path, bibliotheque: Path,
                 incoming: Path, lire=fabrique.lire_metadonnees,
                 fabriquer=fabrique.fabriquer_vignette, dormir=time.sleep,
                 doit_s_arreter=lambda: False):
        self.catalog_db, self.vignettes, self.dossier = catalog_db, vignettes, dossier
        self.bibliotheque, self.incoming = bibliotheque, incoming
        self.lire, self.fabriquer = lire, fabriquer
        self.dormir, self.doit_s_arreter = dormir, doit_s_arreter

    def executer(self, limite: int | None = None) -> dict:
        bilan = {"faites": 0, "erreurs": 0, "dates": 0}
        restants = a_traiter(self.catalog_db, self.vignettes, self.bibliotheque)
        if limite is not None:
            restants = restants[:limite]
        for debut in range(0, len(restants), LOT):
            while synchro_en_cours(self.incoming):
                if self.doit_s_arreter():
                    return bilan
                self.dormir(PAUSE_SYNCHRO_S)
            if self.doit_s_arreter():
                return bilan
            lot = restants[debut:debut + LOT]
            presents = [m for m in lot if Path(m.chemin).is_file()]
            try:
                metas = self.lire([m.chemin for m in presents])
            except Exception:                      # exiftool en panne : on continue sans
                _log.exception("métadonnées illisibles pour un lot")
                metas = {}
            dates = []
            for m in lot:
                meta = metas.get(m.chemin, {})
                try:
                    if m not in presents:
                        raise fabrique.ErreurVignette("fichier absent de la bibliothèque")
                    largeur, hauteur, methode = self.fabriquer(
                        m.chemin, m.c.type, meta, chemin_vignette(self.dossier, m.empreinte))
                    self.vignettes.enregistrer_faite(m.empreinte, largeur, hauteur, methode)
                    bilan["faites"] += 1
                except Exception as e:             # une erreur n'arrête jamais la passe
                    self.vignettes.enregistrer_erreur(m.empreinte, str(e))
                    bilan["erreurs"] += 1
                if m.c.source != "date_prise" and m in presents:
                    recolte = recolter_date(meta, m.nom)
                    if recolte:
                        dates.append((m.empreinte, *recolte))
            bilan["dates"] += ecrire_dates(self.catalog_db, dates)
        return bilan


def _prendre_verrou(chemin: Path):
    """Verrou exclusif non bloquant ; None si un autre recensement tourne."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    f = open(chemin, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Recensement de la galerie : vignettes et dates.")
    parser.add_argument("--une-passe", action="store_true", help="une seule passe, puis s'arrêter")
    parser.add_argument("--limite", type=int, default=None, help="au plus N médias")
    parser.add_argument("--reessayer-erreurs", action="store_true",
                        help="remettre en file les médias en échec")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    verrou = _prendre_verrou(config.DATA_DIR / "recensement.verrou")
    if verrou is None:
        _log.info("un autre recensement tourne déjà : rien à faire")
        return 0

    arret = {"demande": False}
    signal.signal(signal.SIGTERM, lambda *_: arret.update(demande=True))
    vignettes = Vignettes(config.GALERIE_DB)
    if args.reessayer_erreurs:
        _log.info("%d média(s) en échec remis en file", vignettes.oublier_erreurs())
    passe = Passe(config.CATALOG_DB, vignettes, config.VIGNETTES_DIR, config.LIBRARY_DIR,
                  config.INCOMING_DIR, doit_s_arreter=lambda: arret["demande"])
    while True:
        debut = time.monotonic()
        bilan = passe.executer(limite=args.limite)
        _log.info("passe terminée en %.0f s : %d vignette(s), %d échec(s), %d date(s)",
                  time.monotonic() - debut, bilan["faites"], bilan["erreurs"], bilan["dates"])
        if args.une_passe or arret["demande"]:
            return 0
        for _ in range(INTERVALLE_S):              # repos, interruptible chaque seconde
            if arret["demande"]:
                return 0
            time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Étape 4 : lancer les tests pour les voir passer**

Lancer : `python3 -m pytest tests/test_recensement.py -q`
Attendu : `15 passed`

- [ ] **Étape 5 : valider par mutation**

- retirer `AND date_prise IS NULL` → `test_la_recolte_n_ecrase_jamais…` et `test_ecrire_dates_ne_touche_que_les_trous` tombent ;
- retirer `d.year >= 1900` → vérifier si `test_une_date_nulle_ne_s_ecrit_pas` tombe. Si `_pick_metadata_date` rejette déjà « 0000 » tout seul, ce test ne prouve rien sur NOTRE garde : le noter dans le rapport de tâche et **garder quand même la garde** ;
- supprimer le `try/except` autour de `self.fabriquer` → `test_une_vignette_en_echec…` tombe ;
- ignorer `vignettes.traitees()` dans `a_traiter` → `test_le_recensement_reprend…` tombe.

- [ ] **Étape 6 : commit**

```bash
git add phototheque/recensement.py tests/test_recensement.py
git commit -F - <<'FIN'
feat(galerie): recensement reprenable des vignettes et des dates (#31)

Processus a part, un seul a la fois, en pause pendant une synchro, les
plus recents d'abord. date_prise n'est ecrite que si elle est vide, depuis
les metadonnees ou le nom du fichier, jamais depuis la date systeme.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Tâche 7 : servir vignettes et médias, sans jamais ouvrir un chemin du client

**Fichiers :**
- Modifier : `phototheque/app.py` (dépendance `require_lecteur` juste après `require_admin` ; routes galerie près de `/apk`)
- Test : `tests/test_galerie_routes.py`

**Interfaces :**
- Consomme : `vignettes.EMPREINTE`, `chemin_vignette`, `chemin_moyenne` ; `fabrique.lire_metadonnees`, `fabriquer_moyenne`, `ErreurVignette` ; `mediasort.catalog.Catalog.chemin_de(digest)` ; `mediasort.classify.media_type`
- Produit :
  - `require_lecteur(request, authorization) -> None` : admin (Basic) **ou** appareil (`Bearer`) ;
  - `_media_sur(empreinte: str) -> Path` (404 sinon) ;
  - `GET /galerie/vignette/{empreinte}` (WebP, ou image de remplacement SVG) ;
  - `GET /galerie/moyenne/{empreinte}` (WebP 1280 px, photos ; sinon redirection vers l'original) ;
  - `GET /galerie/original/{empreinte}` (le fichier, réponses partielles `Range`).

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
"""Routes de service de la galerie : authentification, sûreté, Range."""
import base64
import importlib
import time

import pytest
from fastapi.testclient import TestClient

from mediasort.catalog import Catalog

E_PHOTO, E_VIDEO, E_HORS, E_PARTI = "1" * 64, "2" * 64, "3" * 64, "4" * 64


def _client(tmp_path, monkeypatch):
    from phototheque import adminauth
    (tmp_path / "admin").write_text(adminauth.empreinte("secret", iterations=1000))
    for cle, valeur in {
        "LIBRARY_DIR": tmp_path / "Famille", "CATALOG_DB": tmp_path / "cat.db",
        "INCOMING_DIR": tmp_path / "incoming", "DEVICES_DB": tmp_path / "dev.db",
        "JOURNAL_DB": tmp_path / "j.db", "GALERIE_DB": tmp_path / "g.db",
        "VIGNETTES_DIR": tmp_path / "vign", "ADMIN_FILE": tmp_path / "admin",
        "APK_FILE": tmp_path / "app.apk",
    }.items():
        monkeypatch.setenv(cle, str(valeur))
    bib = tmp_path / "Famille"
    (bib / "Photos/2023/06 JUIN").mkdir(parents=True)
    (bib / "Videos/2023/06 JUIN").mkdir(parents=True)
    (bib / "Photos/2023/06 JUIN/IMG_1.jpg").write_bytes(b"\xff\xd8photo")
    video = bib / "Videos/2023/06 JUIN/VID_1.mp4"
    with open(video, "wb") as f:              # 1 Gio creux : n'occupe pas le disque
        f.truncate(1024 ** 3)
    secret = tmp_path / "secret.txt"
    secret.write_text("ne doit jamais sortir")
    cat = Catalog(tmp_path / "cat.db")
    cat.add_media(E_PHOTO, 7, str(bib / "Photos/2023/06 JUIN/IMG_1.jpg"), None, "seed")
    cat.add_media(E_VIDEO, 1024 ** 3, str(video), None, "seed")
    cat.add_media(E_HORS, 1, str(secret), None, "seed")                     # hors bibliothèque
    cat.add_media(E_PARTI, 1, str(bib / "Photos/2023/06 JUIN/parti.jpg"), None, "seed")
    cat.close()
    import phototheque.config as c
    importlib.reload(c)
    import phototheque.app as a
    importlib.reload(a)
    jeton = base64.b64encode(b"admin:secret").decode()
    return a, TestClient(a.app), {"Authorization": f"Basic {jeton}"}


@pytest.mark.parametrize("adresse", [f"/galerie/vignette/{E_PHOTO}",
                                     f"/galerie/original/{E_PHOTO}",
                                     f"/galerie/moyenne/{E_PHOTO}"])
def test_les_routes_de_service_exigent_une_authentification(adresse, tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    assert client.get(adresse).status_code == 401


def test_un_jeton_d_appareil_suffit(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("Téléphone")
    r = client.get(f"/galerie/original/{E_PHOTO}", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200


def test_un_faux_jeton_d_appareil_est_refuse(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/original/{E_PHOTO}", headers={"Authorization": "Bearer faux"})
    assert r.status_code == 401


def test_original_sert_le_fichier(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/original/{E_PHOTO}", headers=adm)
    assert r.status_code == 200 and r.content == b"\xff\xd8photo"


@pytest.mark.parametrize("forgee", ["../../etc/passwd", "5" * 64, "A" * 64, "%2e%2e%2fsecret"])
def test_une_empreinte_forgee_ou_inconnue_repond_404(forgee, tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    assert client.get(f"/galerie/original/{forgee}", headers=adm).status_code == 404


def test_un_chemin_de_catalogue_hors_bibliotheque_n_est_jamais_ouvert(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/original/{E_HORS}", headers=adm)
    assert r.status_code == 404 and b"jamais sortir" not in r.content


def test_original_d_un_fichier_disparu_repond_404(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    assert client.get(f"/galerie/original/{E_PARTI}", headers=adm).status_code == 404


def test_une_requete_range_sur_une_grande_video_ne_lit_pas_le_fichier(tmp_path, monkeypatch):
    # Spec §9.6, leçon de l'issue #21 : 1 Gio lu en mémoire prendrait des
    # secondes et 1 Gio de RAM ; une réponse partielle n'en lit que 1 Kio.
    a, client, adm = _client(tmp_path, monkeypatch)
    debut = time.monotonic()
    r = client.get(f"/galerie/original/{E_VIDEO}", headers={**adm, "Range": "bytes=0-1023"})
    assert r.status_code == 206
    assert len(r.content) == 1024
    assert r.headers["content-range"] == f"bytes 0-1023/{1024 ** 3}"
    assert time.monotonic() - debut < 2


def test_vignette_absente_donne_l_image_de_remplacement(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/vignette/{E_PHOTO}", headers=adm)
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")


def test_vignette_presente_est_servie_en_webp(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    from phototheque.vignettes import chemin_vignette
    p = chemin_vignette(tmp_path / "vign", E_PHOTO)
    p.parent.mkdir(parents=True)
    p.write_bytes(b"RIFF....WEBP")
    r = client.get(f"/galerie/vignette/{E_PHOTO}", headers=adm)
    assert r.headers["content-type"] == "image/webp" and r.content == b"RIFF....WEBP"


def test_moyenne_d_une_video_redirige_vers_l_original(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/moyenne/{E_VIDEO}", headers=adm, follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == f"/galerie/original/{E_VIDEO}"


def test_moyenne_ratee_redirige_vers_l_original(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    def rate(*args, **kw):
        raise a.fabrique.ErreurVignette("ffmpeg (moyenne) : Invalid data")
    monkeypatch.setattr(a.fabrique, "fabriquer_moyenne", rate)
    monkeypatch.setattr(a.fabrique, "lire_metadonnees", lambda chemins: {})
    r = client.get(f"/galerie/moyenne/{E_PHOTO}", headers=adm, follow_redirects=False)
    assert r.status_code == 307


def test_la_documentation_reste_fermee(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    for chemin in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(chemin, headers=adm).status_code == 404
```

- [ ] **Étape 2 : lancer les tests pour les voir échouer**

Lancer : `python3 -m pytest tests/test_galerie_routes.py -q`
Attendu : ÉCHEC — les routes `/galerie/…` répondent 404, et `test_les_routes…exigent…` voit 404 au lieu de 401.

- [ ] **Étape 3 : écrire les routes**

Dans `phototheque/app.py`, compléter les imports du module (à côté des imports
`from . import …` existants) :

```python
from mediasort.catalog import Catalog      # déjà importé ? ne pas le doubler
from mediasort.classify import media_type
from . import fabrique, vignettes
from starlette.responses import RedirectResponse, Response
```

Juste après la définition de `require_admin` :

```python
def require_lecteur(request: Request, authorization: str = Header(default="")) -> None:
    """Lecture de la galerie : l'administrateur (mot de passe) OU un
    téléphone appairé (jeton d'appareil). Spec §8 : l'application n'a pas le
    mot de passe d'administration, elle a un jeton — elle doit pouvoir lire
    la galerie, jamais l'administrer."""
    if authorization.startswith("Bearer "):
        require_device(request, authorization)
        return
    require_admin(request, authorization)
```

Près de la route `/apk` :

```python
# --- galerie (issue #31) : servir, en lecture seule ---------------------
#
# Règle de sûreté (spec §7) : une requête porte une EMPREINTE, jamais un
# chemin. On la résout par le catalogue, puis on vérifie que le chemin obtenu
# est bien sous la bibliothèque avant d'ouvrir quoi que ce soit — un catalogue
# abîmé ou trafiqué ne doit pas suffire à faire sortir /etc/passwd.

_IMAGE_REMPLACEMENT = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160">'
    '<rect width="160" height="160" fill="#8a8f98" fill-opacity="0.25"/>'
    '<text x="80" y="86" font-family="sans-serif" font-size="13" text-anchor="middle"'
    ' fill="#5b606a">vignette à venir</text></svg>')

# Une seule taille intermédiaire fabriquée à la fois : le NUC a 2 cœurs, et
# la synchronisation du téléphone reste prioritaire.
_verrou_moyenne = threading.Lock()


def _media_sur(empreinte: str) -> Path:
    """Chemin du média désigné par `empreinte`, ou 404. Jamais d'autre fichier."""
    if not vignettes.EMPREINTE.fullmatch(empreinte):
        raise HTTPException(status_code=404, detail="média inconnu")
    cat = Catalog(config.CATALOG_DB)
    try:
        chemin = cat.chemin_de(empreinte)
    finally:
        cat.close()
    if not chemin:
        raise HTTPException(status_code=404, detail="média inconnu")
    racine = config.LIBRARY_DIR.resolve()
    p = Path(chemin).resolve()
    if not p.is_relative_to(racine) or not p.is_file():
        raise HTTPException(status_code=404, detail="média introuvable")
    return p


@app.get("/galerie/vignette/{empreinte}")
def galerie_vignette(empreinte: str, _: None = Depends(require_lecteur)):
    if not vignettes.EMPREINTE.fullmatch(empreinte):
        raise HTTPException(status_code=404, detail="média inconnu")
    p = vignettes.chemin_vignette(config.VIGNETTES_DIR, empreinte)
    if p.is_file():
        return FileResponse(p, media_type="image/webp",
                            headers={"Cache-Control": "private, max-age=86400"})
    # Pas encore recensé : la galerie fonctionne quand même (spec §4).
    return Response(_IMAGE_REMPLACEMENT, media_type="image/svg+xml",
                    headers={"Cache-Control": "no-store"})


@app.get("/galerie/original/{empreinte}")
def galerie_original(empreinte: str, _: None = Depends(require_lecteur)):
    # FileResponse lit par blocs et honore l'en-tête Range (Starlette ≥ 0.39) :
    # une vidéo de 900 Mo n'est jamais chargée en mémoire (leçon de #21).
    p = _media_sur(empreinte)
    return FileResponse(p, content_disposition_type="inline", filename=p.name)


@app.get("/galerie/moyenne/{empreinte}")
def galerie_moyenne(empreinte: str, _: None = Depends(require_lecteur)):
    p = _media_sur(empreinte)
    original = RedirectResponse(f"/galerie/original/{empreinte}", status_code=307)
    if media_type(p.suffix) != "photo":
        return original
    cible = vignettes.chemin_moyenne(config.VIGNETTES_DIR, empreinte)
    if not cible.is_file():
        with _verrou_moyenne:
            if not cible.is_file():
                try:
                    meta = fabrique.lire_metadonnees([str(p)]).get(str(p), {})
                    fabrique.fabriquer_moyenne(str(p), meta.get("Orientation"), cible)
                except Exception:
                    # Format que ffmpeg ne sait pas lire (HEIC…) : le navigateur
                    # tentera l'original, c'est mieux qu'une page d'erreur.
                    return original
    return FileResponse(cible, media_type="image/webp",
                        headers={"Cache-Control": "private, max-age=86400"})
```

Vérifier que `threading`, `Path`, `FileResponse` et `HTTPException` sont déjà
importés en tête de `app.py` (ils le sont pour les routes existantes) ;
n'ajouter que ce qui manque.

- [ ] **Étape 4 : lancer les tests pour les voir passer, puis toute la suite**

Lancer : `python3 -m pytest tests/test_galerie_routes.py -q`
Attendu : `18 passed`
Puis : `python3 -m pytest -q`
Attendu : toute la suite verte (383 tests avant ce plan + ceux des tâches 1 à 7).

- [ ] **Étape 5 : valider par mutation**

- retirer `not p.is_relative_to(racine) or` → `test_un_chemin_de_catalogue_hors_bibliotheque…` tombe ;
- remplacer `FileResponse(p, …)` par `Response(p.read_bytes())` dans `galerie_original` → `test_une_requete_range…` tombe (206 attendu) ;
- remplacer `Depends(require_lecteur)` par rien sur une route → le test paramétré d'authentification tombe ;
- dans `require_lecteur`, appeler `require_admin` même pour un `Bearer` → `test_un_jeton_d_appareil_suffit` tombe.

- [ ] **Étape 6 : commit**

```bash
git add phototheque/app.py tests/test_galerie_routes.py
git commit -F - <<'FIN'
feat(galerie): servir vignettes et medias, empreinte et jamais chemin (#31)

require_lecteur accepte l'administrateur ou un telephone appaire. Le
chemin vient du catalogue et doit rester sous la bibliotheque. Reponses
partielles Range pour la video, taille intermediaire a la demande.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Tâche 8 : les pages — galerie en accueil, média en grand, admin à `/admin`

**Fichiers :**
- Modifier : `phototheque/web.py` (nouvelles fonctions en fin de fichier ; bloc galerie dans `admin_html` ; liens `href="/"` des pages d'administration → `/admin`)
- Modifier : `phototheque/app.py` (route `/` → galerie, nouvelle route `/admin`, route `/galerie/media/{empreinte}`)
- Modifier : `tests/test_app.py` (`ADRESSES_ADMIN` : ajouter `"/admin"`) et les tests qui lisent la page d'admin à `/`
- Test : `tests/test_galerie_routes.py` (ajouts)

> **Thème :** les pages de la galerie reprennent `STYLE` de `web.py` (via
> `_document`), donc la palette de l'admin en clair et en sombre. Aucune
> couleur propre à la galerie. C'est la moitié « galerie » de l'issue #43.

**Interfaces :**
- Consomme : `galerie_vue.construire_vue`, `lire_filtres`, `lire_niveau`, `url`, `VueGalerie`, `libelle_…` ; `galerie_index.index_courant` ; `vignettes.Vignettes(...).bilan()` ; `_media_sur`
- Produit :
  - `web.galerie_html(vue: VueGalerie) -> str` ;
  - `web.media_html(empreinte: str, nom: str, type_: str, taille: int, retour: str) -> str` ;
  - `web.admin_html(…, recensement: dict | None = None)` (nouveau paramètre facultatif, en dernier) ;
  - routes `GET /` (galerie), `GET /admin`, `GET /galerie/media/{empreinte}`.

- [ ] **Étape 1 : écrire les tests qui échouent** (à la suite de `tests/test_galerie_routes.py`)

```python
# --- pages -----------------------------------------------------------------

def test_l_accueil_est_la_galerie_et_liste_les_annees(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    from phototheque import galerie_index
    galerie_index.vider_cache()
    r = client.get("/", headers=adm)
    assert r.status_code == 200
    assert "2023" in r.text and 'href="/?annee=2023"' in r.text
    assert 'href="/admin"' in r.text


def test_l_accueil_exige_une_authentification(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    assert client.get("/").status_code == 401


def test_un_mois_affiche_sa_grille_de_vignettes(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    from phototheque import galerie_index
    galerie_index.vider_cache()
    r = client.get("/?annee=2023&mois=6", headers=adm)
    assert f'src="/galerie/vignette/{E_PHOTO}"' in r.text
    assert f'href="/galerie/media/{E_PHOTO}"' in r.text


def test_les_filtres_se_retrouvent_dans_le_formulaire(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get("/?type=video&du=2023-01-01", headers=adm)
    assert 'value="2023-01-01"' in r.text
    assert '<option value="video" selected>' in r.text


def test_page_media_photo(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/media/{E_PHOTO}", headers=adm)
    assert f'src="/galerie/moyenne/{E_PHOTO}"' in r.text


def test_page_media_video_propose_le_telechargement_et_le_dit(tmp_path, monkeypatch):
    # Spec §6 : pas de transcodage ; on propose le téléchargement, et on le dit.
    a, client, adm = _client(tmp_path, monkeypatch)
    r = client.get(f"/galerie/media/{E_VIDEO}", headers=adm)
    assert "<video" in r.text and f'src="/galerie/original/{E_VIDEO}"' in r.text
    assert "download" in r.text and "télécharger" in r.text.lower()


def test_page_media_inconnue_repond_404(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    assert client.get(f"/galerie/media/{'9' * 64}", headers=adm).status_code == 404


def test_un_nom_piege_est_echappe_partout(tmp_path, monkeypatch):
    # Point de vigilance n° 1 : « A&K », « Les Bouchons d'Aur » existent sur le NUC.
    a, client, adm = _client(tmp_path, monkeypatch)
    nom = "L'été & <moi>.jpg"
    p = tmp_path / "Famille/Photos/2023/06 JUIN" / nom
    p.write_bytes(b"\xff\xd8")
    e = "6" * 64
    cat = Catalog(tmp_path / "cat.db")
    cat.add_media(e, 2, str(p), None, "seed")
    cat.close()
    from phototheque import galerie_index
    galerie_index.vider_cache()
    for adresse in ("/?annee=2023&mois=6", f"/galerie/media/{e}"):
        texte = client.get(adresse, headers=adm).text
        assert "<moi>" not in texte, adresse
        assert "&lt;moi&gt;" in texte, adresse


def test_l_admin_est_a_son_adresse_et_montre_le_recensement(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    from phototheque.vignettes import Vignettes
    base = Vignettes(tmp_path / "g.db")
    base.enregistrer_faite(E_PHOTO, 400, 300, "photo")
    base.enregistrer_erreur(E_VIDEO, "x")
    base.close()
    r = client.get("/admin", headers=adm)
    assert r.status_code == 200
    assert "Galerie" in r.text and "1 vignette" in r.text and "1 en échec" in r.text
```

Dans `tests/test_app.py`, ajouter `"/admin"` à `ADRESSES_ADMIN`. Chercher les
tests qui lisent la page d'administration par `client.get("/"…)` et
attendent son contenu (appareils, disque, APK, médias non rangés) :
`grep -n 'get("/"' tests/test_app.py`. Les faire pointer sur `"/admin"`.

- [ ] **Étape 2 : lancer les tests pour les voir échouer**

Lancer : `python3 -m pytest tests/test_galerie_routes.py tests/test_app.py -q`
Attendu : ÉCHEC — `/` rend encore l'admin, `/admin` et `/galerie/media/…` répondent 404.

- [ ] **Étape 3 : écrire les pages**

À la fin de `phototheque/web.py` :

```python
# --- galerie (issue #31) --------------------------------------------------

STYLE_GALERIE = """
.filtres { display:flex; flex-wrap:wrap; gap:8px; align-items:end; margin:12px 0; }
.filtres label { display:flex; flex-direction:column; font-size:.85em; }
.blocs { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; padding:0; list-style:none; }
.blocs a { display:block; padding:8px 12px; border-radius:8px;
           background:var(--surface); text-decoration:none; }
.blocs .n { opacity:.7; font-size:.85em; margin-left:6px; }
.grille { display:grid; grid-template-columns:repeat(auto-fill, minmax(160px, 1fr));
          gap:4px; margin:8px 0 16px; }
.grille img { width:100%; aspect-ratio:1; object-fit:cover; display:block;
              border-radius:4px; background:var(--surface); }
.fil a { margin-right:6px; }
.pages { display:flex; gap:12px; margin:16px 0; }
.grand img, .grand video { max-width:100%; max-height:80vh; display:block; margin:0 auto; }
"""


def _selecteur(nom: str, valeur: str | None, options: list[tuple[str, str]]) -> str:
    lignes = "".join(
        f'<option value="{v}"{" selected" if v == (valeur or "") else ""}>{html.escape(t)}</option>'
        for v, t in options)
    return f'<select name="{nom}">{lignes}</select>'


def galerie_html(vue) -> str:
    """Page de la galerie : fil d'Ariane, filtres, blocs (années, mois ou
    jours) et grille de vignettes. `vue` est un `galerie_vue.VueGalerie`."""
    f = vue.filtres
    fil = " › ".join(f'<a href="{html.escape(u)}">{html.escape(t)}</a>' for t, u in vue.fil)
    # Le formulaire recolle la position courante (année/mois/jour) en champs
    # cachés : changer un filtre ne doit pas ramener à l'accueil.
    caches = "".join(
        f'<input type="hidden" name="{k}" value="{html.escape(v)}">'
        for k, v in (vue.position or {}).items())
    formulaire = (
        f'<form class="filtres" method="get" action="/">{caches}'
        f'<label>Du <input type="date" name="du" value="{f.du.isoformat() if f.du else ""}"></label>'
        f'<label>Au <input type="date" name="au" value="{f.au.isoformat() if f.au else ""}"></label>'
        "<label>Type " + _selecteur("type", f.type, [("", "Tout"), ("photo", "Photos"),
                                                       ("video", "Vidéos")]) + "</label>"
        "<label>Origine " + _selecteur("origine", f.origine, [
            ("", "Toutes"), ("appareil", "Appareil photo"), ("whatsapp", "WhatsApp"),
            ("autre", "Autres dossiers")]) + "</label>"
        '<button class="bouton" type="submit">Filtrer</button></form>')
    message = f'<p class="alerte">{html.escape(vue.message)}</p>' if vue.message else ""
    blocs = ""
    if vue.blocs:
        blocs = '<ul class="blocs">' + "".join(
            f'<li><a href="{html.escape(u)}">{html.escape(t)}<span class="n">{_nombre(n)}</span></a></li>'
            for t, u, n in vue.blocs) + "</ul>"
    grille = ""
    for titre, medias in vue.groupes:
        cases = "".join(
            f'<a href="/galerie/media/{m.empreinte}" title="{html.escape(m.nom)}">'
            f'<img loading="lazy" src="/galerie/vignette/{m.empreinte}" alt="{html.escape(m.nom)}"></a>'
            for m in medias)
        entete = f"<h2>{html.escape(titre)}</h2>" if titre else ""
        grille += f'{entete}<div class="grille">{cases}</div>'
    if not vue.blocs and not vue.groupes:
        grille = '<p class="vide">Aucun média ne correspond à ces filtres.</p>'
    pages = ""
    if vue.pages > 1:
        prec = f'<a href="{html.escape(vue.precedente)}">‹ Précédente</a>' if vue.precedente else ""
        suiv = f'<a href="{html.escape(vue.suivante)}">Suivante ›</a>' if vue.suivante else ""
        pages = f'<div class="pages">{prec}<span>page {vue.page} / {vue.pages}</span>{suiv}</div>'
    corps = (
        f'<header><h1>{html.escape(vue.titre)}</h1>'
        f'<p class="hote">{_nombre(vue.total)} média(s) · '
        '<a href="/admin">Administration</a></p></header>'
        f'<nav class="fil">{fil}</nav>{formulaire}{message}{blocs}{grille}{pages}')
    return _document("phototheque — galerie", corps, STYLE_GALERIE)


def media_html(empreinte: str, nom: str, type_: str, taille: int, retour: str) -> str:
    """Un média en grand. Photo : taille intermédiaire. Vidéo : l'original en
    lecture partielle, et le téléchargement proposé — le NUC ne transcode pas."""
    nom_sur = html.escape(nom)
    if type_ == "video":
        contenu = (
            f'<video controls preload="metadata" src="/galerie/original/{empreinte}"></video>'
            '<p class="indice">Si la vidéo ne se lance pas, ce navigateur ne sait pas lire '
            f'son format : <a download href="/galerie/original/{empreinte}">la télécharger</a>.</p>')
    else:
        contenu = (
            f'<img src="/galerie/moyenne/{empreinte}" alt="{nom_sur}">'
            f'<p class="indice"><a download href="/galerie/original/{empreinte}">'
            "Télécharger l'original</a></p>")
    corps = (
        f"<header><h1>{nom_sur}</h1>"
        f'<p class="hote">{_go(taille)} · <a href="{html.escape(retour)}">Retour</a></p></header>'
        f'<div class="grand">{contenu}</div>')
    return _document(f"phototheque — {nom_sur}", corps, STYLE_GALERIE)
```

`galerie_html` lit `vue.position` : ajouter à `VueGalerie` (tâche 3) le champ
`position: dict = field(default_factory=dict)`, rempli dans `construire_vue`
avec les clés présentes parmi `annee`, `mois`, `jour` (valeurs en texte). Et
ajouter à `tests/test_galerie_vue.py` :

```python
def test_la_position_est_gardee_pour_le_formulaire():
    v = gv.construire_vue(_index(), gi.Filtres(), annee=2023, mois=6)
    assert v.position == {"annee": "2023", "mois": "6"}
```

Dans `construire_vue`, juste avant chaque `return`, poser
`position = {k: str(v) for k, v in (("annee", annee), ("mois", mois), ("jour", jour)) if v is not None}`
et le passer à `VueGalerie(…, position=position)`.

Dans `admin_html`, ajouter le paramètre `recensement: dict | None = None`
(en dernier) et, avant la section des appareils, ce bloc :

```python
    galerie = ""
    if recensement is not None:
        faites, erreurs = recensement["faites"], recensement["erreurs"]
        total = recensement.get("total", 0)
        derniere = recensement.get("derniere")
        galerie = (
            '<section class="carte"><h2>Galerie</h2>'
            f"<p>{_nombre(faites)} vignette(s) sur {_nombre(total)} médias · "
            f"{_nombre(erreurs)} en échec"
            + (f" · dernière le {html.escape(str(derniere))}" if derniere else "")
            + '</p><p><a class="bouton" href="/">Ouvrir la galerie</a></p></section>')
```

puis l'insérer dans le corps de la page, à côté des autres sections. Enfin,
remplacer dans `web.py` chaque lien « Retour » des pages d'administration
(`href="/"` : historique, recherche, évènements, appairage, détail d'une
synchro) par `href="/admin"` — `grep -n 'href="/"' phototheque/web.py`.

Dans `phototheque/app.py`, la route `/` existante devient `/admin` (renommer
la fonction `admin` telle quelle, et lui passer le bilan du recensement) :

```python
def _etat_recensement() -> dict | None:
    """Bilan du recensement pour l'admin ; None si la base est illisible —
    la page d'administration ne doit jamais tomber pour ça."""
    try:
        base = vignettes.Vignettes(config.GALERIE_DB)
        try:
            bilan = base.bilan()
        finally:
            base.close()
        bilan["total"] = len(galerie_index.index_courant(config.CATALOG_DB, config.LIBRARY_DIR))
        return bilan
    except Exception:
        _log_journal.exception("bilan du recensement illisible")
        return None


@app.get("/admin", response_class=HTMLResponse)
def admin(_: None = Depends(require_admin)) -> str:
    d = stats.disk_stats(config.LIBRARY_DIR)
    return web.admin_html(devices().list(), d, _media_counts(),
                          apk.infos(config.APK_FILE),
                          quarantaine.lister(config.INCOMING_DIR / quarantaine.DOSSIER),
                          _etat_recensement())


@app.get("/", response_class=HTMLResponse)
def galerie(annee: str = "", mois: str = "", jour: str = "", du: str = "", au: str = "",
            type: str = "", origine: str = "", page: int = 1,
            _: None = Depends(require_lecteur)) -> str:
    """Page d'accueil : la galerie (spec §3). Lecture seule."""
    filtres, message = galerie_vue.lire_filtres(du, au, type, origine)
    index = galerie_index.index_courant(config.CATALOG_DB, config.LIBRARY_DIR)
    vue = galerie_vue.construire_vue(
        index, filtres, galerie_vue.lire_niveau(annee), galerie_vue.lire_niveau(mois),
        galerie_vue.lire_niveau(jour), page, message)
    return web.galerie_html(vue)


@app.get("/galerie/media/{empreinte}", response_class=HTMLResponse)
def galerie_media(empreinte: str, _: None = Depends(require_lecteur)) -> str:
    p = _media_sur(empreinte)
    m = galerie_index.index_courant(config.CATALOG_DB, config.LIBRARY_DIR).trouver(empreinte)
    type_ = media_type(p.suffix) or "photo"
    retour = "/"
    if m is not None and m.c.annee is not None:
        retour = galerie_vue.url(galerie_index.Filtres(), annee=m.c.annee, mois=m.c.mois)
    return web.media_html(empreinte, p.name, type_, p.stat().st_size, retour)
```

Ajouter `galerie_index` et `galerie_vue` aux imports `from . import …`.
Vérifier que le nom de journal utilisé pour les erreurs (`_log_journal`) est
bien celui qui existe dans `app.py` ; sinon utiliser le `logging.getLogger`
déjà présent.

- [ ] **Étape 4 : lancer les tests pour les voir passer, puis toute la suite**

Lancer : `python3 -m pytest tests/test_galerie_routes.py tests/test_galerie_vue.py tests/test_app.py -q`
Attendu : tout vert.
Puis : `python3 -m pytest -q` — toute la suite verte.

- [ ] **Étape 5 : valider par mutation**

- retirer `html.escape` sur `m.nom` dans la grille → `test_un_nom_piege_est_echappe_partout` tombe ;
- retirer les champs cachés du formulaire → écrire vite un test qui le prouve s'il n'y en a pas (le formulaire d'un mois doit contenir `name="annee" value="2023"`), puis vérifier qu'il tombe ;
- remettre `/` sur l'admin → `test_l_accueil_est_la_galerie…` tombe.

- [ ] **Étape 6 : vérifier à l'œil, en local**

```bash
LIBRARY_DIR=/tmp/galerie-essai CATALOG_DB=/tmp/galerie-essai.db DOCS_PUBLIQUES= \
  python3 -m uvicorn phototheque.app:app --port 8799 --ws none
```

Après avoir créé quelques fichiers et lignes de catalogue d'essai, ouvrir
`http://127.0.0.1:8799/` dans un navigateur en **navigation privée** (voir
CLAUDE.md : l'authentification Basic est gardée en mémoire par le
navigateur), en clair et en sombre, et à la largeur d'un téléphone. Nettoyer
`/tmp/galerie-essai*` ensuite.

- [ ] **Étape 7 : commit**

```bash
git add phototheque/web.py phototheque/app.py phototheque/galerie_vue.py \
        tests/test_galerie_routes.py tests/test_galerie_vue.py tests/test_app.py
git commit -F - <<'FIN'
feat(galerie): la galerie devient l'accueil, l'administration passe a /admin (#31)

Annees, mois, jours et grille, filtres par dates, type et origine, media
en grand (video : lecture partielle et telechargement propose). L'admin
montre l'avancement du recensement.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Tâche 9 : déployer le recensement, documenter, valider sur le NUC

**Fichiers :**
- Créer : `deploy/phototheque-recensement.service`
- Modifier : `deploy/install.sh` (étape « 8/9 Installation et démarrage »)
- Modifier : `tests/test_deploy.py`
- Modifier : `docs/DEPLOIEMENT.md`, `CLAUDE.md`, et les messages qui annoncent l'admin à `/` (`deploy/install.sh`, `deploy/envoyer-apk.sh`, `docs/APPLICATION-ANDROID.md` : « page d'admin » → `/admin`)

**Interfaces :**
- Consomme : `python3 -m phototheque.recensement` (tâche 6)
- Produit : l'unité `phototheque-recensement.service`, installée et démarrée par `install.sh`.

- [ ] **Étape 1 : écrire les tests qui échouent** (dans `tests/test_deploy.py`)

```python
def test_l_unite_du_recensement_est_discrete():
    """Le NUC a 2 cœurs : le recensement passe après tout le reste."""
    unite = (LIB.parent / "phototheque-recensement.service").read_text()
    assert "-m phototheque.recensement" in unite
    assert "Nice=19" in unite
    assert "IOSchedulingClass=idle" in unite
    assert "RequiresMountsFor=/media/izquierdo/Famille" in unite


def test_install_installe_et_demarre_le_recensement():
    script = (LIB.parent / "install.sh").read_text()
    assert "phototheque-recensement.service" in script
    assert "systemctl enable phototheque-recensement.service" in script
    assert "systemctl restart phototheque-recensement.service" in script
```

- [ ] **Étape 2 : lancer les tests pour les voir échouer**

Lancer : `python3 -m pytest tests/test_deploy.py -q -k recensement`
Attendu : ÉCHEC, `FileNotFoundError` sur l'unité.

- [ ] **Étape 3 : écrire l'unité et l'installation**

`deploy/phototheque-recensement.service` :

```ini
[Unit]
Description=phototheque (recensement de la galerie : vignettes et dates)
After=network-online.target phototheque.service
# Lit les médias : n'a rien à faire tant que Famille n'est pas monté.
RequiresMountsFor=/media/izquierdo/Famille

[Service]
User=izquierdo
WorkingDirectory=/home/izquierdo/phone_camera_import
ExecStart=/home/izquierdo/.venv-server/bin/python -m phototheque.recensement
# Priorité la plus basse, processeur ET disque : la réception des photos du
# téléphone passe toujours avant (spec §4). Le recensement s'interrompt en
# plus de lui-même pendant une synchronisation.
Nice=19
IOSchedulingClass=idle
CPUQuota=50%
MemoryMax=400M
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Dans `deploy/install.sh`, juste après le bloc
`sudo systemctl restart ${SERVICE}.service` de l'étape 8/9 :

```bash
# Le recensement de la galerie (issue #31) : son propre service, discret
# (nice 19, E/S au repos), reprenable. Le redémarrer après un git pull lui
# fait relire son code ; il reprend là où il en était.
sudo cp deploy/phototheque-recensement.service /etc/systemd/system/phototheque-recensement.service
sudo systemctl daemon-reload
sudo systemctl enable phototheque-recensement.service
sudo systemctl restart phototheque-recensement.service
info "recensement de la galerie activé et démarré"
```

Remplacer, dans `install.sh` et `envoyer-apk.sh`, les messages qui donnent
`https://…:8787/` comme « page d'administration » par `https://…:8787/admin`
(`grep -n "8787/" deploy/*.sh`). Le test de déploiement existant qui
vérifierait ce texte doit suivre.

- [ ] **Étape 4 : lancer les tests pour les voir passer, puis toute la suite**

Lancer : `python3 -m pytest -q`
Attendu : toute la suite verte.

- [ ] **Étape 5 : documenter**

Dans `docs/DEPLOIEMENT.md`, une section « La galerie et son recensement » :
- ce que fait le service, où vont les vignettes (`~/.local/share/phototheque/vignettes/`, ~1,1 Go attendu), et la base `~/phototheque_galerie.db` ;
- suivre l'avancement : bloc « Galerie » de `/admin`, ou `journalctl -u phototheque-recensement -f` ;
- durée attendue : environ une nuit pour l'arriéré (mesure du 25/09), puis quelques secondes par import ;
- relancer les échecs : `sudo systemctl stop phototheque-recensement && ~/.venv-server/bin/python -m phototheque.recensement --reessayer-erreurs --une-passe && sudo systemctl start phototheque-recensement` ;
- retour arrière : `sudo systemctl disable --now phototheque-recensement` ; la galerie reste utilisable (images de remplacement) ;
- ce qu'il écrit dans le catalogue : `date_prise` et `source_date` (`metadata`/`filename`) des seules lignes où `date_prise` était vide — **sauvegarder `~/mediasort_catalog.db` avant le premier démarrage** (`cp ~/mediasort_catalog.db ~/mediasort_catalog.db.avant-recensement`).

Dans `CLAUDE.md` : l'état (galerie écrite), la nouvelle adresse de l'admin
(`/admin`), la commande de suivi, et ce piège : l'adresse `/` du NUC n'est
plus l'administration.

- [ ] **Étape 6 : commit**

```bash
git add deploy/phototheque-recensement.service deploy/install.sh deploy/envoyer-apk.sh \
        tests/test_deploy.py docs/DEPLOIEMENT.md docs/APPLICATION-ANDROID.md CLAUDE.md
git commit -F - <<'FIN'
feat(deploy): service du recensement de la galerie, nice 19 et E/S au repos (#31)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

- [ ] **Étape 7 : valider sur le NUC (avec le mainteneur)**

Le NUC a son adresse du moment : `avahi-resolve -4 -n IZQUIERDO-NUC.local`.
Son lien WiFi bat : sonder plusieurs fois.

1. Sauvegarde du catalogue, **avant** tout : `cp ~/mediasort_catalog.db ~/mediasort_catalog.db.avant-recensement`.
2. `git pull` sur la branche, puis **faire lancer au mainteneur** `./deploy/install.sh` (sudo = vrai terminal). Vérifier ensuite que les deux services sont actifs et récents : `systemctl is-active phototheque phototheque-recensement` et `systemctl show -p ActiveEnterTimestamp phototheque-recensement`.
3. Après 15 minutes : `journalctl -u phototheque-recensement --since "-15min"`, et le bloc « Galerie » de `/admin`. Relever le débit réel (vignettes/minute) et le comparer à l'estimation (~150/min en moyenne sur la nuit).
4. **Orientation** (non vérifiable sur le poste, faute d'`exiftool`) : trouver une photo en portrait avec `exiftool -if '$Orientation# == 6' -p '$Directory/$FileName' -r /media/izquierdo/Famille/Photos/2023 | head -3`, attendre sa vignette, et vérifier dans la galerie qu'elle est **debout**. Si elle est couchée ou tournée deux fois, ffmpeg 8 applique peut-être déjà l'orientation malgré `-noautorotate` : corriger `fabrique.py` et ajouter un test de non-régression.
5. **Vidéo** : ouvrir une vidéo de plus de 500 Mo dans la galerie, la faire avancer au milieu. `journalctl -u phototheque` doit montrer des réponses `206`, et `systemctl status phototheque` une mémoire stable.
6. **Pause pendant une synchro** : lancer une sauvegarde depuis le téléphone ; le journal du recensement ne doit plus avancer pendant qu'elle tourne.
7. `/docs`, `/redoc`, `/openapi.json` : toujours **404** sur le NUC.
8. Au matin : bloc « Galerie » à (presque) 100 %. Relever le nombre d'échecs et leurs raisons (`--reessayer-erreurs` n'est utile que si la cause a disparu), et le nombre de dates comblées :
   `python3 -c "import sqlite3;c=sqlite3.connect('file:$HOME/mediasort_catalog.db?mode=ro',uri=True);print(c.execute('select source_date,count(*) from medias group by 1').fetchall())"`.
9. Supprimer la sauvegarde du catalogue **seulement avec l'accord du mainteneur**.

---

## Auto-relecture (faite à l'écriture du plan)

- **Couverture de la spec :**
  - §4 recensement : tâches 5 et 6 ; §4 avancement dans l'admin : tâche 8 ; §4 volumétrie, taille intermédiaire à la demande : tâche 7.
  - §5 navigation et filtres : tâches 1 à 3 et 8.
  - §6 vignettes seules dans la grille, `Range`, pas de transcodage : tâches 7 et 8.
  - §7 sûreté : tâches 4 et 7 ; `/docs` fermé : tâches 7 et 9.
  - §8 : hors plan, sauf `require_lecteur` (tâche 7).
  - §9, tests 1 à 8 :
    1. tâche 1 ;
    2. tâches 2 et 3 ;
    3. tâche 6 (reprise) ;
    4. tâche 6 (vignette en échec) ;
    5. tâche 7 (chemin venu du client) ;
    6. tâche 7 (`Range`) ;
    7. tâches 7 et 8 (authentification) ;
    8. tâche 6 (dates).
  - §11 : répondu par les mesures en tête de plan.
- **Types et noms croisés :**
  - `Media.c`, `Classement.source == "date_prise"` (tâches 1, 2 et 6) ;
  - `Filtres` (tâches 2, 3 et 8) ;
  - `VueGalerie.position` ajouté à la tâche 8, avec la retouche de la tâche 3 écrite noir sur blanc ;
  - `Vignettes.bilan()` → `faites`/`erreurs`/`derniere`, complété de `total` par `_etat_recensement` (tâche 8) ;
  - `chemin_vignette`/`chemin_moyenne` (tâches 4, 6 et 7) ;
  - `fabrique.ErreurVignette` (tâches 5, 6 et 7).
- **Reste à trancher à l'exécution, écrit comme tel :**
  - le comportement réel de ffmpeg 8 sur l'orientation EXIF (tâche 9, point 4) ;
  - la garde `year >= 1900`, peut-être redondante avec `_pick_metadata_date` (tâche 6, mutation).
