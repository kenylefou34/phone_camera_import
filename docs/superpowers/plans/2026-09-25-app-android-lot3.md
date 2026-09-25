# Application Android — lot 3 : thème, onglet galerie, #42 et #39 — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** l'application reprend le thème de l'admin, gagne un onglet « Galerie »
qui affiche la galerie du NUC dans une `WebView` épinglée et authentifiée par
un cookie de session court, et corrige #42 (journal) et #39 (interruption).

**Architecture:** côté serveur, un magasin de sessions en mémoire
(`phototheque/galerie_sessions.py`) échange le jeton d'appareil contre un
cookie qui n'ouvre que les routes de lecture de la galerie. Côté application,
toute décision est une fonction ou une machine d'états pure testée sur JVM
(épinglage, cookie, confinement, suivi de chargement, `EtatGalerie`,
`Navigation`, `Interruption`) ; seul l'assemblage final (`VueGalerie`,
`ModeleGalerie`, `EcranGalerie`, barre d'onglets) touche Android, et il est
couvert par la recette.

**Tech Stack:** Python 3 / FastAPI / pytest ; Kotlin, Jetpack Compose
(BOM 2024.06.00, material3 1.2.x), OkHttp 4.12, `android.webkit.WebView`,
WorkManager 2.9, JUnit4 + mockwebserver.

**Spec:** `docs/superpowers/specs/2026-09-25-app-android-lot3-design.md`

## Global Constraints

- **Rien n'est installé** sur le téléphone ni sur le NUC, aucun service redémarré : code, tests, documentation seulement (l'étape 11 de la recette du lot 2 tourne).
- Commentaires et documentation **en français** ; messages de commit **sans accents** (sujet et corps), toujours par `git commit -F - <<'FIN'` (jamais `-m` s'il y a des accents graves), terminés par la ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Tests serveur : `python3 -m pytest -q` depuis la racine du dépôt.
- Tests app : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests '<classe>'` (**jamais** `./gradlew test --tests`, qui échoue sur ce projet).
- Chaque test nouveau est **validé par mutation** : casser volontairement le code, constater que c'est ce test-là qui tombe, remettre le code.
- Un test ne fabrique jamais sa valeur attendue avec la fonction qu'il teste.
- `minSdk` 29, `targetSdk` 34, `compileSdk` 34 : ne pas les changer. Aucune nouvelle dépendance Gradle (pas d'`androidx.webkit`, pas de `material-icons-extended`, pas de `navigation-compose`).
- Pas de couleur dynamique (Material You) ; pas d'affichage bord à bord ; icône du lanceur inchangée.
- Nom du cookie : `phototheque_galerie` ; durée : `43200` s (12 h) ; au plus `8` sessions vivantes par appareil.
- Texte « pas à la maison » (identique à l'accueil) : `Serveur introuvable — vous n'êtes probablement pas chez vous.`
- Après **tout** ajout ou changement de route dans `phototheque/app.py` : `/docs`, `/redoc`, `/openapi.json` doivent rester en 404.

## Review Focus

1. **Boucle de `401`** : `onPageFinished` est aussi appelé après une page en erreur ; s'il remettait à zéro le compteur de `401`, la `WebView` rééchangerait sans fin contre un serveur qui refuse. → `SuiviChargement` (tâche 9) ne signale « chargée » qu'une navigation sans erreur ; test dédié.
2. **Le NUC change d'adresse entre deux ouvertures** (`.21` → `.31`, documenté) : le chemin mémorisé doit être recollé à la **nouvelle** origine, jamais recharger l'ancienne adresse. → `CheminGalerie.aCharger` (tâche 9) ; test dédié.
3. **Origine IPv6** (`https://[fe80::1]:8787`, ce que produit la découverte) : le confinement ne doit ni la refuser ni accepter un autre hôte. → test IPv6 dans `ConfinementTest` (tâche 9).
4. **Cookie ET mot de passe dans la même requête** (un navigateur de bureau qui aurait les deux) : l'en-tête `Authorization` doit primer, et un mauvais cookie ne doit pas masquer un bon mot de passe. → test dans la tâche 6.
5. **Valeur de cookie hostile** (point-virgule, espace, retour à la ligne renvoyés par un serveur) : elle ne doit jamais injecter d'attribut. → `CookieGalerie.chaine` refuse (tâche 9) ; test dédié.

---

## Carte des fichiers

| Fichier | Rôle | Tâche |
|---|---|---|
| `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Theme.kt` (créé) | `Palette`, `Jetons`, `schema()`, `ThemePhototheque`, `Intertitre`, `LocalPalette` | 1 |
| `android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/ThemeTest.kt` (créé) | aucun rôle hors palette | 1 |
| `android/app/src/main/res/values{,-night}/{themes,colors}.xml` (créés) | thème de fenêtre clair/sombre | 2 |
| `android/app/src/main/AndroidManifest.xml` | `android:theme` | 2 |
| `MainActivity.kt`, `ui/Ecrans.kt`, `synchro/ServiceSynchro.kt` | thème appliqué | 2, 12 |
| `tests/test_theme_app.py` (créé) | anti-dérive `web.py` ↔ app | 2 |
| `synchro/Orchestrateur.kt`, `synchro/TravailSynchro.kt`, `synchro/Journal.kt` | #42 | 3 |
| `synchro/VerrouSynchro.kt`, `synchro/Interruption.kt` (créé), `synchro/TravailSynchro.kt` | #39 | 4 |
| `phototheque/galerie_sessions.py` (créé), `tests/test_galerie_sessions.py` (créé) | magasin de sessions | 5 |
| `phototheque/app.py`, `tests/test_galerie_routes.py` | échange, `require_lecteur` | 6 |
| `phototheque/web.py`, `docs/CONTRAT-APP.md` | liens masqués, contrat | 7 |
| `reseau/Contrat.kt`, `reseau/ClientServeur.kt`, `reseau/Decouverte.kt` | échange côté app | 8 |
| `galerie/EpinglageWebView.kt`, `galerie/CookieGalerie.kt`, `galerie/Confinement.kt`, `galerie/SuiviChargement.kt`, `galerie/CheminGalerie.kt` (créés) | décisions pures de la `WebView` | 9 |
| `galerie/EtatGalerie.kt` (créé) | machine d'états | 10 |
| `ui/Navigation.kt` | onglet `GALERIE` | 11 |
| `galerie/VueGalerie.kt`, `galerie/ModeleGalerie.kt`, `ui/EcranGalerie.kt`, `ui/BarreOnglets.kt` (créés), `res/drawable/ic_onglet_*.xml` (créés), `ui/ModeleAccueil.kt`, `MainActivity.kt` | assemblage | 12 |
| `docs/APPLICATION-ANDROID.md`, `CLAUDE.md` | documentation, recette | 13 |

Chemins Kotlin abrégés : `X.kt` = `android/app/src/main/kotlin/fr/izquierdo/phototheque/X.kt` ; tests sous `android/app/src/test/kotlin/fr/izquierdo/phototheque/`.

---

### Task 1: Le thème Compose (#43, partie code)

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Theme.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/ThemeTest.kt`

**Interfaces:**
- Produces: `data class Palette(plane, surface, ink, ink2, muted, line, accent, warning, critical: Color)` avec `border` et `accentDoux` ; `object Jetons { val CLAIR: Palette; val SOMBRE: Palette }` ; `fun schema(p: Palette, sombre: Boolean): ColorScheme` ; `@Composable fun ThemePhototheque(sombre: Boolean = isSystemInDarkTheme(), contenu: @Composable () -> Unit)` ; `@Composable fun Intertitre(texte: String, modifier: Modifier = Modifier)` ; `val LocalPalette`.
- Le **format des lignes** `nom = Color(0xFFRRGGBB),` dans `Jetons` est un contrat : la tâche 2 les relit par expression régulière.

- [ ] **Step 1: Write the failing test**

```kotlin
package fr.izquierdo.phototheque.ui

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.Color
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Issue #43 : l'application doit avoir l'air du même produit que l'admin.
 * Un rôle Material oublié garde sa valeur par défaut — le violet de
 * Material 3 — et ressurgit dans un interrupteur ou l'indicateur d'onglet.
 */
class ThemeTest {

    /** Les 36 rôles de ColorScheme (material3 1.2.x), un par un. */
    private fun roles(s: ColorScheme): Map<String, Color> = mapOf(
        "primary" to s.primary, "onPrimary" to s.onPrimary,
        "primaryContainer" to s.primaryContainer, "onPrimaryContainer" to s.onPrimaryContainer,
        "inversePrimary" to s.inversePrimary,
        "secondary" to s.secondary, "onSecondary" to s.onSecondary,
        "secondaryContainer" to s.secondaryContainer, "onSecondaryContainer" to s.onSecondaryContainer,
        "tertiary" to s.tertiary, "onTertiary" to s.onTertiary,
        "tertiaryContainer" to s.tertiaryContainer, "onTertiaryContainer" to s.onTertiaryContainer,
        "background" to s.background, "onBackground" to s.onBackground,
        "surface" to s.surface, "onSurface" to s.onSurface,
        "surfaceVariant" to s.surfaceVariant, "onSurfaceVariant" to s.onSurfaceVariant,
        "surfaceTint" to s.surfaceTint,
        "inverseSurface" to s.inverseSurface, "inverseOnSurface" to s.inverseOnSurface,
        "error" to s.error, "onError" to s.onError,
        "errorContainer" to s.errorContainer, "onErrorContainer" to s.onErrorContainer,
        "outline" to s.outline, "outlineVariant" to s.outlineVariant, "scrim" to s.scrim,
        "surfaceBright" to s.surfaceBright, "surfaceDim" to s.surfaceDim,
        "surfaceContainer" to s.surfaceContainer, "surfaceContainerHigh" to s.surfaceContainerHigh,
        "surfaceContainerHighest" to s.surfaceContainerHighest,
        "surfaceContainerLow" to s.surfaceContainerLow,
        "surfaceContainerLowest" to s.surfaceContainerLowest,
    )

    private fun admises(p: Palette, inverse: Palette): Set<Color> = setOf(
        p.plane, p.surface, p.ink, p.ink2, p.muted, p.line, p.accent, p.warning,
        p.critical, p.accentDoux, inverse.surface, inverse.ink, inverse.accent,
        Color.White, Color.Black)

    @Test fun aucun_role_du_schema_clair_ne_sort_de_la_palette_de_l_admin() {
        roles(schema(Jetons.CLAIR, sombre = false)).forEach { (nom, c) ->
            assertTrue("$nom hors palette en clair : $c", c in admises(Jetons.CLAIR, Jetons.SOMBRE))
        }
    }

    @Test fun aucun_role_du_schema_sombre_ne_sort_de_la_palette_de_l_admin() {
        roles(schema(Jetons.SOMBRE, sombre = true)).forEach { (nom, c) ->
            assertTrue("$nom hors palette en sombre : $c", c in admises(Jetons.SOMBRE, Jetons.CLAIR))
        }
    }

    @Test fun la_liste_des_roles_verifies_est_complete() {
        // Une montée du BOM Compose peut ajouter des rôles : ce test tombe
        // alors, au lieu de laisser un nouveau rôle violet passer inaperçu.
        // Color est une classe « inline » : ses accesseurs rendent un long.
        val accesseurs = ColorScheme::class.java.declaredMethods.count {
            it.name.startsWith("get") && it.parameterCount == 0 && it.returnType == java.lang.Long.TYPE
        }
        assertEquals(accesseurs, roles(lightColorScheme()).size)
    }

    @Test fun le_bleu_de_l_admin_remplace_le_violet_par_defaut() {
        assertNotEquals(lightColorScheme().primary, schema(Jetons.CLAIR, false).primary)
        // Valeurs recopiées de phototheque/web.py (--accent), pas relues du code testé.
        assertEquals(Color(0xFF2A78D6), schema(Jetons.CLAIR, false).primary)
        assertEquals(Color(0xFF3987E5), schema(Jetons.SOMBRE, true).primary)
    }

    @Test fun une_erreur_n_a_jamais_de_fond_rouge() {
        // L'admin n'en a aucun : un état critique y est un texte ou un
        // liseré, toujours doublé d'un mot.
        assertEquals(Jetons.CLAIR.surface, schema(Jetons.CLAIR, false).errorContainer)
        assertEquals(Jetons.SOMBRE.surface, schema(Jetons.SOMBRE, true).errorContainer)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests 'fr.izquierdo.phototheque.ui.ThemeTest'`
Expected: FAIL à la compilation (`Unresolved reference: schema`, `Jetons`, `Palette`).

- [ ] **Step 3: Write minimal implementation**

`ui/Theme.kt` :

```kotlin
package fr.izquierdo.phototheque.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.compositeOver
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import java.util.Locale

/**
 * Les jetons de couleur de l'interface d'administration du NUC (issue #43).
 *
 * Recopiés de `STYLE` dans `phototheque/web.py`, sous leur nom CSS (`--ink-2`
 * devient `ink2`). **Ne pas modifier une valeur ici sans la modifier là-bas** :
 * `tests/test_theme_app.py` compare les deux, et relit ces lignes par
 * expression régulière — garder le format `nom = Color(0xFFRRGGBB),`.
 */
data class Palette(
    val plane: Color,
    val surface: Color,
    val ink: Color,
    val ink2: Color,
    val muted: Color,
    val line: Color,
    val accent: Color,
    val warning: Color,
    val critical: Color,
) {
    /** `--border` de l'admin : le texte à 10 % d'opacité. */
    val border: Color get() = ink.copy(alpha = 0.10f)

    /** Fond d'un élément « choisi » (indicateur d'onglet) : l'accent très
     *  atténué, posé sur une carte. L'admin n'a pas d'équivalent : c'est la
     *  seule couleur dérivée du thème. */
    val accentDoux: Color get() = accent.copy(alpha = 0.14f).compositeOver(surface)
}

object Jetons {
    val CLAIR = Palette(
        plane = Color(0xFFF9F9F7),
        surface = Color(0xFFFCFCFB),
        ink = Color(0xFF0B0B0B),
        ink2 = Color(0xFF52514E),
        muted = Color(0xFF898781),
        line = Color(0xFFE1E0D9),
        accent = Color(0xFF2A78D6),
        warning = Color(0xFFFAB219),
        critical = Color(0xFFD03B3B),
    )

    // `warning` et `critical` ne sont pas redéfinis en sombre dans web.py :
    // on garde les mêmes valeurs.
    val SOMBRE = Palette(
        plane = Color(0xFF0D0D0D),
        surface = Color(0xFF1A1A19),
        ink = Color(0xFFFFFFFF),
        ink2 = Color(0xFFC3C2B7),
        muted = Color(0xFF898781),
        line = Color(0xFF2C2C2A),
        accent = Color(0xFF3987E5),
        warning = Color(0xFFFAB219),
        critical = Color(0xFFD03B3B),
    )
}

/**
 * Le schéma Material 3 construit sur les jetons. TOUS les rôles sont posés :
 * un rôle laissé à sa valeur par défaut fait ressurgir le violet de
 * Material 3 (vérifié par ThemeTest).
 */
fun schema(p: Palette, sombre: Boolean): ColorScheme {
    val inverse = if (sombre) Jetons.CLAIR else Jetons.SOMBRE
    val base = if (sombre) darkColorScheme() else lightColorScheme()
    return base.copy(
        primary = p.accent, onPrimary = Color.White,
        primaryContainer = p.accentDoux, onPrimaryContainer = p.ink,
        inversePrimary = inverse.accent,
        secondary = p.accent, onSecondary = Color.White,
        secondaryContainer = p.accentDoux, onSecondaryContainer = p.ink,
        tertiary = p.accent, onTertiary = Color.White,
        tertiaryContainer = p.accentDoux, onTertiaryContainer = p.ink,
        background = p.plane, onBackground = p.ink,
        surface = p.surface, onSurface = p.ink,
        surfaceVariant = p.plane, onSurfaceVariant = p.ink2,
        // Material teinte les surfaces surélevées avec cette couleur : la
        // poser sur la surface elle-même supprime la teinte bleutée.
        surfaceTint = p.surface,
        inverseSurface = inverse.surface, inverseOnSurface = inverse.ink,
        error = p.critical, onError = Color.White,
        // Pas de fond rouge : l'admin n'en a aucun.
        errorContainer = p.surface, onErrorContainer = p.ink,
        outline = p.line, outlineVariant = p.line,
        scrim = Color.Black,
        surfaceBright = p.surface, surfaceDim = p.plane,
        surfaceContainer = p.surface, surfaceContainerHigh = p.surface,
        surfaceContainerHighest = p.surface, surfaceContainerLow = p.surface,
        surfaceContainerLowest = p.surface,
    )
}

/** La palette courante, pour les jetons qui n'ont pas de rôle Material
 *  (`muted`, `warning`, `border`). */
val LocalPalette = staticCompositionLocalOf { Jetons.CLAIR }

// Les `.carte` de l'admin ont un rayon de 14 px, ses boutons de 9 px.
private val FORMES = Shapes(small = RoundedCornerShape(9.dp), medium = RoundedCornerShape(14.dp))

// Le h1 de l'admin : 26 px, graisse 640 (Roboto non variable l'arrondit à 600).
private val TYPOGRAPHIE = Typography().let {
    it.copy(headlineMedium = it.headlineMedium.copy(
        fontSize = 26.sp, fontWeight = FontWeight.W600, letterSpacing = (-0.015).em))
}

/** Remplace le `MaterialTheme { }` nu : clair ou sombre comme le téléphone,
 *  comme l'admin suit le navigateur. Pas de couleur dynamique (Material You). */
@Composable
fun ThemePhototheque(sombre: Boolean = isSystemInDarkTheme(), contenu: @Composable () -> Unit) {
    val p = if (sombre) Jetons.SOMBRE else Jetons.CLAIR
    CompositionLocalProvider(LocalPalette provides p) {
        MaterialTheme(colorScheme = schema(p, sombre), typography = TYPOGRAPHIE, shapes = FORMES) {
            // Sans Surface, rien ne peint le fond : il venait de la fenêtre.
            Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                contenu()
            }
        }
    }
}

/** L'intertitre de l'admin (`h2`) : petites capitales grises espacées. */
@Composable
fun Intertitre(texte: String, modifier: Modifier = Modifier) {
    Text(texte.uppercase(Locale.FRENCH), modifier,
         color = LocalPalette.current.muted,
         style = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.W600, letterSpacing = 0.07.em))
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests 'fr.izquierdo.phototheque.ui.ThemeTest'`
Expected: PASS (5 tests).
Si `lightColorScheme()` lève `Method ... not mocked` (appel au framework Android) : ne pas ajouter Robolectric ; remplacer dans le test la construction réelle par la vérification de la table de correspondance (une `Map<String, (Palette) -> Color>` exposée par `Theme.kt` et utilisée par `schema()`), et le signaler dans le rapport de tâche.

- [ ] **Step 5: Validate by mutation**

Retirer temporairement `secondaryContainer = p.accentDoux, onSecondaryContainer = p.ink,` de `schema()` → `aucun_role_du_schema_clair_…` doit tomber en citant `secondaryContainer`. Retirer une entrée de `roles()` → `la_liste_des_roles_verifies_est_complete` doit tomber. Remettre.

- [ ] **Step 6: Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Theme.kt android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/ThemeTest.kt
git commit -F - <<'FIN'
feat(app): theme Compose construit sur les jetons de l'admin (#43)

Palette recopiee de STYLE (web.py), schema Material 3 dont tous les
roles sont poses (aucun violet par defaut ne survit), typographie et
formes de l'admin, intertitre en petites capitales.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 2: Le thème appliqué — fenêtre, écrans, notification, anti-dérive (#43)

**Files:**
- Create: `android/app/src/main/res/values/themes.xml`, `android/app/src/main/res/values-night/themes.xml`, `android/app/src/main/res/values/colors.xml`, `android/app/src/main/res/values-night/colors.xml`
- Modify: `android/app/src/main/AndroidManifest.xml` (balise `<application>`, vers la ligne 45)
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/MainActivity.kt:10,64`
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Ecrans.kt` (`Bandeau` vers la ligne 289, intertitres)
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/ServiceSynchro.kt:50`
- Test: `tests/test_theme_app.py`

**Interfaces:**
- Consumes: `Jetons`, `ThemePhototheque`, `Intertitre`, `LocalPalette` (tâche 1).
- Produces: le style `@style/Theme.Phototheque` (clair en `values`, sombre en `values-night`) — la tâche 12 en dépend pour que la `WebView` reçoive `prefers-color-scheme: dark`.

- [ ] **Step 1: Write the failing test**

`tests/test_theme_app.py` :

```python
"""Issue #43 : l'application et l'admin partagent les mêmes couleurs.

Les jetons sont recopiés à la main dans l'application (Theme.kt) et dans les
ressources de fenêtre Android (colors.xml). Ce test empêche la dérive : il
tombe si l'un des côtés change seul.
"""
import re
from pathlib import Path

from phototheque.web import STYLE

RACINE = Path(__file__).resolve().parent.parent
THEME_KT = RACINE / "android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Theme.kt"
COULEURS_CLAIR = RACINE / "android/app/src/main/res/values/colors.xml"
COULEURS_SOMBRE = RACINE / "android/app/src/main/res/values-night/colors.xml"

_JETON_CSS = re.compile(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\b")
_JETON_KT = re.compile(r"(\w+) = Color\(0xFF([0-9A-Fa-f]{6})\)")


def _css() -> tuple[dict, dict]:
    """(clair, sombre) : le sombre hérite du clair, comme en CSS."""
    debut = STYLE.index(":root {")
    clair_txt = STYLE[debut:STYLE.index("}", debut)]
    media = STYLE.index("prefers-color-scheme: dark")
    d = STYLE.index(":root {", media)
    sombre_txt = STYLE[d:STYLE.index("}", d)]
    clair = {n.replace("-", ""): v.lower() for n, v in _JETON_CSS.findall(clair_txt)}
    sombre = dict(clair)
    sombre.update({n.replace("-", ""): v.lower() for n, v in _JETON_CSS.findall(sombre_txt)})
    return clair, sombre


def _kotlin(nom_bloc: str) -> dict:
    texte = THEME_KT.read_text(encoding="utf-8")
    debut = texte.index(f"val {nom_bloc} = Palette(")
    bloc = texte[debut:texte.index("\n    )", debut)]
    return {n: "#" + v.lower() for n, v in _JETON_KT.findall(bloc)}


def _plane_xml(chemin: Path) -> str:
    m = re.search(r'<color name="plane">(#[0-9a-fA-F]{6})</color>', chemin.read_text())
    assert m, f"couleur « plane » absente de {chemin}"
    return m.group(1).lower()


def test_les_jetons_clairs_de_l_app_sont_ceux_de_l_admin():
    clair, _ = _css()
    assert _kotlin("CLAIR") == clair


def test_les_jetons_sombres_de_l_app_sont_ceux_de_l_admin():
    _, sombre = _css()
    assert _kotlin("SOMBRE") == sombre


def test_le_fond_de_fenetre_android_suit_l_admin():
    clair, sombre = _css()
    assert _plane_xml(COULEURS_CLAIR) == clair["plane"]
    assert _plane_xml(COULEURS_SOMBRE) == sombre["plane"]


def test_la_lecture_du_css_n_est_pas_vide():
    # Garde-fou du test lui-même : une regex qui ne trouve rien rendrait les
    # trois tests ci-dessus vrais sur deux dictionnaires vides.
    clair, sombre = _css()
    assert {"plane", "surface", "ink", "ink2", "muted", "line", "accent",
            "warning", "critical"} <= clair.keys()
    assert sombre["plane"] != clair["plane"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_theme_app.py`
Expected: FAIL — `test_le_fond_de_fenetre_android_suit_l_admin` (fichier `colors.xml` absent) ; les deux tests de jetons passent déjà grâce à la tâche 1 (c'est attendu : ils la verrouillent).

- [ ] **Step 3: Write the resources**

`res/values/colors.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- Fond de fenêtre, recopié de --plane (phototheque/web.py). Le reste des
     couleurs vit dans ui/Theme.kt. tests/test_theme_app.py compare. -->
<resources>
    <color name="plane">#F9F9F7</color>
</resources>
```

`res/values-night/colors.xml` : identique avec `#0D0D0D`.

`res/values/themes.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- Thème de FENÊTRE (issue #43). Compose peint l'intérieur ; ce thème
     peint ce qui s'affiche avant lui (plus de flash blanc au lancement en
     sombre) et, surtout, dit à la WebView si l'activité est claire ou
     sombre : avec targetSdk >= 33, elle ne transmet
     prefers-color-scheme: dark à la page que si isLightTheme est faux. -->
<resources>
    <style name="Theme.Phototheque" parent="android:Theme.Material.Light.NoActionBar">
        <item name="android:windowBackground">@color/plane</item>
        <item name="android:statusBarColor">@color/plane</item>
        <item name="android:navigationBarColor">@color/plane</item>
        <item name="android:windowLightStatusBar">true</item>
        <item name="android:windowLightNavigationBar">true</item>
    </style>
</resources>
```

`res/values-night/themes.xml` : même nom de style, parent `android:Theme.Material.NoActionBar`, `windowLightStatusBar` et `windowLightNavigationBar` à `false`, mêmes trois couleurs.

Manifeste — ajouter l'attribut à `<application>` (garder les autres) :

```xml
    <application android:label="Photothèque"
                 android:theme="@style/Theme.Phototheque"
                 android:icon="@mipmap/ic_launcher"
```

- [ ] **Step 4: Apply the theme in Kotlin**

`MainActivity.kt` : remplacer l'import `androidx.compose.material3.MaterialTheme` par `import fr.izquierdo.phototheque.ui.ThemePhototheque`, et `MaterialTheme {` (ligne 64) par `ThemePhototheque {`.

`ui/Ecrans.kt`, `Bandeau` :

```kotlin
@Composable
private fun Bandeau(texte: String) {
    // Liseré rouge sur une carte, jamais de fond rouge : c'est la règle de
    // l'admin (.etiquette.critical). Le texte dit toujours de quoi il s'agit.
    Card(Modifier.fillMaxWidth().padding(bottom = 16.dp),
         colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
         border = BorderStroke(1.dp, MaterialTheme.colorScheme.error)) {
        Text(texte, Modifier.padding(16.dp))
    }
}
```
(import `androidx.compose.foundation.BorderStroke`).

Intertitres — remplacer par `Intertitre("…")` :
- `Text("Fichier en cours", style = MaterialTheme.typography.labelMedium)` ;
- `Text("Bilan du serveur", style = MaterialTheme.typography.titleMedium)` ;
- `Text("Dossiers trouvés sur le téléphone", style = MaterialTheme.typography.titleMedium)` ;
- puis `grep -n "titleMedium\|titleLarge\|labelMedium" android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/*.kt` et convertir chaque **titre de section** restant (un `Text` à libellé fixe suivi d'un contenu), pas les lignes de données (« Paquet 3 · 2 validés » reste en `labelMedium`).
- `Text("Dernière synchronisation", style = MaterialTheme.typography.titleLarge)` devient le titre d'écran : `style = MaterialTheme.typography.headlineMedium`, comme « Réglages ».

Règle « couleur jamais seule » : relire chaque `color = MaterialTheme.colorScheme.error` de `ui/*.kt` et vérifier qu'il colore un **texte qui dit lui-même le problème**. Le compteur de jours de l'accueil (`Ecrans.kt:55-57`) passe en rouge : vérifier que le message d'alerte s'affiche dans le même état (`alerte` vrai) ; sinon, le signaler dans le rapport de tâche sans rien inventer.

`synchro/ServiceSynchro.kt`, dans le `NotificationCompat.Builder`, après `.setSmallIcon(...)` :

```kotlin
            // Le bleu de l'admin (issue #43) ; la plupart des versions
            // d'Android ne l'utilisent que pour teinter la petite icône.
            .setColor(Jetons.CLAIR.accent.toArgb())
```
(imports `androidx.compose.ui.graphics.toArgb`, `fr.izquierdo.phototheque.ui.Jetons`).

- [ ] **Step 5: Run tests and build**

Run: `python3 -m pytest -q tests/test_theme_app.py` → PASS (4 tests).
Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest assembleDebug` → BUILD SUCCESSFUL, tous les tests verts.
Contrôle du manifeste FUSIONNÉ : `grep -c 'Theme.Phototheque' android/app/build/intermediates/merged_manifests/debug/processDebugManifest/AndroidManifest.xml` → au moins 1.

- [ ] **Step 6: Validate by mutation**

Changer `#F9F9F7` en `#F9F9F8` dans `values/colors.xml` → `test_le_fond_de_fenetre_android_suit_l_admin` tombe. Changer `--accent: #2a78d6` en `#2a78d7` dans `web.py` → `test_les_jetons_clairs_…` tombe. Remettre les deux.

- [ ] **Step 7: Commit**

```bash
git add android/app/src/main/res android/app/src/main/AndroidManifest.xml android/app/src/main/kotlin tests/test_theme_app.py
git commit -F - <<'FIN'
feat(app): theme de l'admin applique a la fenetre, aux ecrans et a la notification (#43)

Theme de fenetre clair/sombre (la WebView ne transmet
prefers-color-scheme: dark qu'a une activite sombre), bandeaux a
lisere critique au lieu d'un fond rouge, intertitres de l'admin,
notification a l'accent. Un test Python compare les jetons de web.py
a Theme.kt et aux colors.xml.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 3: #42 — un arrêt subi ne s'écrit plus « terminée »

**Files:**
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Orchestrateur.kt` (après `data class Bilan`, vers la ligne 36)
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/TravailSynchro.kt:27-43` (`IssueSynchro`), `:274-276`, `:299-311`, `:346`
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Journal.kt:25-47`
- Modify: `docs/APPLICATION-ANDROID.md:608-614`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/JournalTest.kt`, `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/BilanTest.kt` (créé)

**Interfaces:**
- Produces: `fun Bilan.pourLEcran(arretDemande: Boolean): Bilan` (top-level, `Orchestrateur.kt`) ; `IssueSynchro.arretSubi: Boolean = false`.

- [ ] **Step 1: Write the failing tests**

`synchro/BilanTest.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** « Sauvegarde interrompue. » est une phrase sur une DÉCISION de
 *  l'utilisateur : l'écran ne doit la dire que pour un arrêt demandé. */
class BilanTest {
    private fun bilan(interrompu: Boolean) =
        Bilan(1, 0, 0, revoque = false, bilanServeur = emptyMap(), interrompu = interrompu)

    @Test fun un_arret_demande_reste_interrompu_a_l_ecran() {
        assertTrue(bilan(true).pourLEcran(arretDemande = true).interrompu)
    }

    @Test fun un_arret_subi_n_est_pas_annonce_comme_interrompu_a_l_ecran() {
        assertFalse(bilan(true).pourLEcran(arretDemande = false).interrompu)
    }

    @Test fun un_bilan_complet_ne_devient_jamais_interrompu() {
        assertFalse(bilan(false).pourLEcran(arretDemande = true).interrompu)
    }
}
```

Ajouter à `JournalTest` :

```kotlin
    @Test fun un_arret_subi_ne_s_ecrit_pas_terminee() {
        // Issue #42 : vu cinq fois le 25/09 (téléphone débranché pendant
        // une passe automatique), écrit « terminée » alors qu'aucun dossier
        // n'avait été lu.
        assertEquals("arrêtée par le système (contrainte perdue ou relance) : " +
                     "0 envoyés, 0 refusés, 0 en échec, dossiers non lus",
            Journal.decrire(IssueSynchro(bilan = bilan(), arretSubi = true)))
    }

    @Test fun un_arret_subi_apres_des_envois_garde_ses_comptes() {
        assertEquals("arrêtée par le système (contrainte perdue ou relance) : " +
                     "4 envoyés, 1 refusés, 0 en échec, 2 dossiers",
            Journal.decrire(IssueSynchro(bilan = bilan(4, 1), arretSubi = true,
                dossiersVus = mapOf("a" to 1, "b" to 2))))
    }

    @Test fun une_revocation_prime_sur_un_arret_subi() {
        assertEquals("appareil révoqué par le serveur",
            Journal.decrire(IssueSynchro(revoque = true, arretSubi = true)))
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests 'fr.izquierdo.phototheque.synchro.BilanTest' --tests 'fr.izquierdo.phototheque.synchro.JournalTest'`
Expected: FAIL à la compilation (`pourLEcran` privée à un paramètre de moins ; `arretSubi` inconnu).

- [ ] **Step 3: Implement**

`Orchestrateur.kt`, juste après la fermeture de `data class Bilan(...)` :

```kotlin
/**
 * Le bilan tel que l'ÉCRAN doit l'annoncer.
 *
 * « Sauvegarde interrompue. » est une phrase sur une DÉCISION de
 * l'utilisateur. Or `isStopped` vaut aussi vrai pour une contrainte réseau
 * perdue ou un arrêt système : l'annoncer ainsi serait faux. Les règles
 * internes (réussite, reprise) et le JOURNAL lisent le bilan BRUT.
 *
 * Fonction pure et publique (elle était privée dans TravailSynchro et lisait
 * un drapeau du companion) : c'est ce qui la rend vérifiable (issue #42).
 */
fun Bilan.pourLEcran(arretDemande: Boolean): Bilan = copy(interrompu = interrompu && arretDemande)
```

`TravailSynchro.kt` :
- supprimer la méthode privée `private fun Bilan.pourLEcran(): Bilan = ...` et son commentaire (ligne ~335-346) ;
- dans `IssueSynchro`, ajouter en dernier champ :

```kotlin
    // Issue #42 : un arrêt que l'utilisateur n'a PAS demandé (contrainte
    // perdue, relance du système). Jamais affiché — l'écran ne doit pas dire
    // « interrompue par vous » — mais écrit dans le journal, qui sert
    // justement à démêler après coup ce qu'une passe automatique a fait.
    val arretSubi: Boolean = false,
```
- fin réussie (ligne ~274) :

```kotlin
            publier(IssueSynchro(
                bilan = bilan.pourLEcran(arretDemande), revoque = bilan.revoque,
                dossiersVus = dossiersVus, dossiersNouveaux = nouveaux,
                arretSubi = bilan.interrompu && !arretDemande))
```
- branche `catch (e: CancellationException)` : remplacer l'appel `publier(IssueSynchro(bilan = (bilanPartiel ?: Bilan(...)).pourLEcran(), dossiersVus = dossiersVus))` par (garder le long commentaire existant au-dessus) :

```kotlin
            // `copy(interrompu = true)` et pas seulement sur le repli : dans
            // CETTE branche, la synchro s'est arrêtée à coup sûr, même si le
            // dernier bilan partiel avait été publié avant l'arrêt.
            val brut = (bilanPartiel ?: Bilan(0, 0, 0, revoque = false,
                                              bilanServeur = emptyMap(),
                                              interrompu = true)).copy(interrompu = true)
            publier(IssueSynchro(
                bilan = brut.pourLEcran(arretDemande),
                dossiersVus = dossiersVus,
                arretSubi = !arretDemande,
            ))
```

`Journal.kt`, `decrire` :

```kotlin
    fun decrire(issue: IssueSynchro): String {
        val bilan = issue.bilan
        return when {
            issue.revoque -> "appareil révoqué par le serveur"
            issue.erreur != null -> "en erreur : ${issue.erreur}"
            issue.serveurIntrouvable -> "serveur introuvable sur le réseau (pas une panne)"
            // Issue #42 : AVANT le cas général. Le bilan d'un arrêt subi a
            // été nettoyé pour l'écran (`interrompu` retiré) : sans ce cas,
            // il s'écrivait « terminée » alors qu'aucun dossier n'avait été lu.
            bilan != null && issue.arretSubi ->
                "arrêtée par le système (contrainte perdue ou relance) : ${comptes(issue, bilan)}"
            bilan != null ->
                "${if (bilan.interrompu) "interrompue" else "terminée"} : ${comptes(issue, bilan)}"
            else -> "sans issue publiée"
        }
    }

    private fun comptes(issue: IssueSynchro, bilan: Bilan): String {
        // `null` et une carte vide ne disent pas la même chose (voir
        // IssueSynchro.dossiersVus) : on ne les confond pas ici non plus.
        val dossiers = issue.dossiersVus?.let { "${it.size} dossiers" } ?: "dossiers non lus"
        // Issue #36 : le gel coûte une réempreinte à chaque passe ; le
        // journal doit le dire aussi, pas seulement l'accueil.
        val gel = if (bilan.gelesParLaDate.isEmpty()) ""
            else ", horizon gelé par la date de début : " +
                bilan.gelesParLaDate.sorted().joinToString(", ")
        return "${bilan.envoyes} envoyés, ${bilan.refuses} refusés, " +
            "${bilan.echecs} en échec, $dossiers$gel"
    }
```

`docs/APPLICATION-ANDROID.md`, remplacer le paragraphe « **Un arrêt SUBI s'écrit « terminée », pas « interrompue »** … s'écrit `interrompue`. » (lignes ~608-614) par :

```markdown
**Un arrêt SUBI s'écrit « arrêtée par le système »** (issue #42, corrigée au
lot 3). Quand WorkManager arrête une passe parce qu'une contrainte vient de
tomber (téléphone débranché, WiFi perdu), la ligne de sortie dit
`arrêtée par le système (contrainte perdue ou relance) : 0 envoyés, …,
dossiers non lus`. Seul un arrêt demandé par « Interrompre » s'écrit
`interrompue`. Avant le lot 3, un arrêt subi s'écrivait à tort `terminée` ;
dans un journal ancien, « dossiers non lus » en est le signe.
```
Et à la ligne ~503 (« … « dossiers non lus », voir §11) »), vérifier que la phrase reste juste ; la réécrire avec le nouveau libellé si elle cite « terminée ».

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest`
Expected: PASS, suite complète verte.

- [ ] **Step 5: Validate by mutation**

Supprimer le cas `bilan != null && issue.arretSubi ->` → `un_arret_subi_ne_s_ecrit_pas_terminee` tombe (« terminée : … »). Remplacer `interrompu && arretDemande` par `interrompu` → `un_arret_subi_n_est_pas_annonce_…` tombe. Remettre.

- [ ] **Step 6: Commit**

```bash
git add android/app/src docs/APPLICATION-ANDROID.md
git commit -F - <<'FIN'
fix(app): un arret subi s'ecrit « arretee par le systeme » dans le journal

Le journal lisait le bilan deja nettoye pour l'ecran et ecrivait
« terminee » pour une passe arretee par une contrainte perdue.
IssueSynchro porte desormais arretSubi (jamais affiche), et
pourLEcran devient une fonction pure testee.

Closes #42

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 4: #39 — interrompre une manuelle ne touche plus l'automatique

**Files:**
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/VerrouSynchro.kt:40-50`
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Interruption.kt`
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Journal.kt` (`file`)
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/TravailSynchro.kt` (`doWork` : `VerrouSynchro.tenter()` ; `interrompre`, lignes ~393-430)
- Modify: `docs/APPLICATION-ANDROID.md:303-310`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/VerrouSynchroTest.kt`, `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/InterruptionTest.kt` (créé)

**Interfaces:**
- Produces: `Journal.FILE_AUTO = "auto"`, `Journal.FILE_MANUELLE = "manuelle"` ; `VerrouSynchro.tenter(file: String = "file inconnue"): Boolean` ; `VerrouSynchro.detenteur: String?` ; `object Interruption { data class Decision(val annulerAuto: Boolean); fun decider(detenteur: String?): Decision }`.

- [ ] **Step 1: Write the failing tests**

`synchro/InterruptionTest.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Issue #39 : interrompre une sauvegarde MANUELLE repoussait aussi la
 *  passe automatique de six heures. */
class InterruptionTest {
    @Test fun interrompre_une_passe_automatique_l_annule_et_la_replanifie() {
        assertTrue(Interruption.decider("auto").annulerAuto)
    }

    @Test fun interrompre_une_manuelle_laisse_l_automatique_intacte() {
        assertFalse(Interruption.decider("manuelle").annulerAuto)
    }

    @Test fun sans_synchro_en_cours_l_automatique_reste_programmee() {
        // Une manuelle EN ATTENTE d'un réseau ne tient pas le verrou.
        assertFalse(Interruption.decider(null).annulerAuto)
    }
}
```

Ajouter à `VerrouSynchroTest` (reprendre sa remise à zéro existante en `@Before`/`@After`, qui appelle `VerrouSynchro.liberer()`) :

```kotlin
    @Test fun le_verrou_retient_la_file_qui_le_tient() {
        assertTrue(VerrouSynchro.tenter("auto"))
        assertEquals("auto", VerrouSynchro.detenteur)
    }

    @Test fun un_refus_ne_change_pas_le_detenteur() {
        assertTrue(VerrouSynchro.tenter("manuelle"))
        assertFalse(VerrouSynchro.tenter("auto"))
        assertEquals("manuelle", VerrouSynchro.detenteur)
    }

    @Test fun liberer_oublie_le_detenteur() {
        VerrouSynchro.tenter("auto")
        VerrouSynchro.liberer()
        assertNull(VerrouSynchro.detenteur)
    }
```
(ajouter les imports `assertEquals`, `assertNull`, `assertFalse` s'ils manquent).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests 'fr.izquierdo.phototheque.synchro.InterruptionTest' --tests 'fr.izquierdo.phototheque.synchro.VerrouSynchroTest'`
Expected: FAIL à la compilation (`Interruption`, `detenteur` inconnus).

- [ ] **Step 3: Implement**

`Journal.kt` :

```kotlin
    const val FILE_AUTO = "auto"
    const val FILE_MANUELLE = "manuelle"

    fun file(etiquettes: Set<String>): String = when {
        TravailSynchro.NOM_PERIODIQUE in etiquettes -> FILE_AUTO
        TravailSynchro.NOM in etiquettes -> FILE_MANUELLE
        else -> "file inconnue"
    }
```

`VerrouSynchro.kt` :

```kotlin
    /**
     * La file (« manuelle » ou « auto ») de l'exécution qui tient le verrou,
     * `null` s'il est libre. Issue #39 : « Interrompre » doit savoir LAQUELLE
     * arrêter, sans attendre — `getWorkInfosForUniqueWork` est asynchrone, et
     * le bouton de la notification passe par un BroadcastReceiver qui n'a
     * que quelques secondes de vie.
     */
    @Volatile var detenteur: String? = null
        private set

    /** Vrai si on a pris le verrou. Faux si une autre exécution le détient déjà. */
    fun tenter(file: String = "file inconnue"): Boolean {
        if (!pris.compareAndSet(false, true)) return false
        detenteur = file
        return true
    }

    /** Relâche le verrou. Sans effet s'il n'était pas déjà pris. */
    fun liberer() {
        detenteur = null
        pris.set(false)
    }
```

`synchro/Interruption.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

/**
 * Ce que « Interrompre » doit annuler (issue #39).
 *
 * La file manuelle est TOUJOURS annulée (y compris une manuelle en attente
 * d'un réseau, qui ne tient pas encore le verrou). La file automatique ne
 * l'est que si c'est ELLE qui tourne : `cancelUniqueWork` détruit la chaîne
 * périodique, qu'il faut alors replanifier avec six heures de délai — un
 * délai qu'on n'a aucune raison d'imposer quand l'utilisateur n'a arrêté
 * qu'une sauvegarde manuelle.
 *
 * Sûr parce que WorkManager exécute ses travaux dans le processus de
 * l'application : si rien n'y tient le verrou, aucune passe automatique ne
 * tourne. Limite assumée : entre le démarrage d'une passe automatique et sa
 * prise du verrou (quelques millisecondes), un appui la laisse filer ;
 * l'accueil n'affiche « Interrompre » qu'une fois l'avancement publié.
 */
object Interruption {
    data class Decision(val annulerAuto: Boolean)

    fun decider(detenteur: String?): Decision = Decision(annulerAuto = detenteur == Journal.FILE_AUTO)
}
```

`TravailSynchro.kt`, `doWork` : `if (!VerrouSynchro.tenter()) {` devient `if (!VerrouSynchro.tenter(file)) {` (la variable `file` est calculée juste avant).

`TravailSynchro.kt`, `interrompre` — remplacer la KDoc et le corps :

```kotlin
        /**
         * Arrête la synchronisation en cours, et SEULEMENT elle (issue #39).
         *
         * La manuelle est toujours annulée. L'automatique ne l'est que si
         * c'est elle qui tourne (`Interruption.decider`) ; dans ce cas elle
         * est REPROGRAMMÉE derrière, avec six heures de délai :
         * `cancelUniqueWork` ne suspend pas une passe périodique, il
         * **détruit la chaîne**, et un `PeriodicWorkRequest` neuf partirait
         * aussitôt ses contraintes satisfaites — le bouton relancerait ce
         * qu'il vient d'arrêter.
         */
        fun interrompre(context: Context) {
            // Pose AVANT l'annulation : c'est ce drapeau, et non `isStopped`,
            // qui distingue un arret demande d'une coupure subie.
            arretDemande = true
            val detenteur = VerrouSynchro.detenteur
            val decision = Interruption.decider(detenteur)
            val gestionnaire = WorkManager.getInstance(context)
            gestionnaire.cancelUniqueWork(NOM)
            if (decision.annulerAuto) {
                gestionnaire.cancelUniqueWork(NOM_PERIODIQUE)
                // Relu des préférences, et non d'un état en mémoire : ce code
                // tourne aussi depuis le bouton de la NOTIFICATION,
                // application fermée. L'ordre annulation → replanification
                // est garanti (même exécuteur sérialisé de WorkManager).
                planifier(context, MagasinReglages(context).lire().auto, apresUnArret = true)
            }
            Journal.info("interruption demandée : " + when (detenteur) {
                null -> "aucune synchro en cours, passe automatique laissée à son échéance"
                Journal.FILE_AUTO -> "passe automatique arrêtée, reprogrammée dans 6 h"
                else -> "synchro $detenteur arrêtée, passe automatique laissée à son échéance"
            })
        }
```

`docs/APPLICATION-ANDROID.md`, remplacer la section `### « Interrompre » ne déprogramme pas la sauvegarde automatique` (titre et paragraphe, lignes ~303-310) par :

```markdown
### « Interrompre » n'arrête que la synchro en cours

- **Une sauvegarde manuelle** (ou une manuelle encore en attente d'un
  réseau) : elle seule est annulée. La programmation automatique reste
  intacte, à son échéance d'origine (issue #39, corrigée au lot 3 ; avant,
  elle glissait de six heures).
- **Une passe automatique** : elle est annulée puis **reprogrammée** si
  l'interrupteur est coché, avec six heures de délai pour ne pas relancer
  aussitôt ce qu'on vient d'arrêter. Sans cette reprogrammation, un seul
  appui aurait déprogrammé la sauvegarde automatique pour de bon,
  l'interrupteur restant affiché « actif ».

Le journal (`adb logcat -s Phototheque`) écrit une ligne
`interruption demandée : …` qui dit lequel des deux cas s'est produit.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest`
Expected: PASS, suite complète verte.

- [ ] **Step 5: Validate by mutation**

Dans `decider`, remplacer par `Decision(annulerAuto = true)` → `interrompre_une_manuelle_…` et `sans_synchro_…` tombent. Retirer `detenteur = file` de `tenter` → `le_verrou_retient_la_file…` tombe. Remettre.

- [ ] **Step 6: Commit**

```bash
git add android/app/src docs/APPLICATION-ANDROID.md
git commit -F - <<'FIN'
fix(app): interrompre une sauvegarde manuelle laisse l'automatique a son echeance

VerrouSynchro retient la file qui le tient ; Interruption.decider
n'annule et ne replanifie la file periodique que si c'est elle qui
tourne. Lu sans attente, ce qui convient au bouton de la notification.

Closes #39

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 5: Serveur — le magasin de sessions de galerie

**Files:**
- Create: `phototheque/galerie_sessions.py`
- Test: `tests/test_galerie_sessions.py`

**Interfaces:**
- Produces: `NOM_COOKIE = "phototheque_galerie"`, `DUREE_S = 43200`, `MAX_PAR_APPAREIL = 8` ; `class SessionsGalerie(duree_s=DUREE_S, max_par_appareil=MAX_PAR_APPAREIL, horloge=time.monotonic)` avec `ouvrir(appareil: str) -> str`, `appareil(valeur: str | None) -> str | None`, `fermer_appareil(appareil: str) -> int`.

- [ ] **Step 1: Write the failing test**

```python
"""Sessions de la galerie pour l'application (lot 3 de l'app, spec §5.2)."""
import hashlib

from phototheque.galerie_sessions import SessionsGalerie


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_une_session_ouverte_designe_son_appareil():
    s = SessionsGalerie()
    v = s.ouvrir("tel-1")
    assert s.appareil(v) == "tel-1"


def test_la_valeur_est_longue_et_imprevisible():
    s = SessionsGalerie()
    a, b = s.ouvrir("tel-1"), s.ouvrir("tel-1")
    assert a != b
    assert len(a) >= 43                       # 256 bits en base64 url
    assert set(a) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_une_valeur_inconnue_vide_ou_absente_ne_designe_personne():
    s = SessionsGalerie()
    s.ouvrir("tel-1")
    assert s.appareil("inconnue") is None
    assert s.appareil("") is None
    assert s.appareil(None) is None


def test_une_session_expire():
    h = Horloge()
    s = SessionsGalerie(duree_s=60, horloge=h)
    v = s.ouvrir("tel-1")
    h.t += 59
    assert s.appareil(v) == "tel-1"
    h.t += 2
    assert s.appareil(v) is None


def test_fermer_un_appareil_retire_toutes_ses_sessions_et_seulement_les_siennes():
    s = SessionsGalerie()
    a1, a2, b = s.ouvrir("tel-1"), s.ouvrir("tel-1"), s.ouvrir("tel-2")
    assert s.fermer_appareil("tel-1") == 2
    assert s.appareil(a1) is None and s.appareil(a2) is None
    assert s.appareil(b) == "tel-2"


def test_au_dela_du_plafond_la_plus_ancienne_session_tombe():
    s = SessionsGalerie(max_par_appareil=3)
    valeurs = [s.ouvrir("tel-1") for _ in range(4)]
    assert s.appareil(valeurs[0]) is None
    assert all(s.appareil(v) == "tel-1" for v in valeurs[1:])


def test_le_plafond_est_par_appareil():
    s = SessionsGalerie(max_par_appareil=1)
    a = s.ouvrir("tel-1")
    s.ouvrir("tel-2")
    assert s.appareil(a) == "tel-1"


def test_la_valeur_n_est_jamais_gardee_en_clair():
    s = SessionsGalerie()
    v = s.ouvrir("tel-1")
    assert v not in repr(s._sessions)
    assert hashlib.sha256(v.encode()).hexdigest() in s._sessions


def test_les_sessions_expirees_sont_purgees_a_l_ouverture():
    h = Horloge()
    s = SessionsGalerie(duree_s=10, horloge=h)
    s.ouvrir("tel-1")
    h.t += 11
    s.ouvrir("tel-2")
    assert len(s._sessions) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_galerie_sessions.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'phototheque.galerie_sessions'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Sessions de la galerie pour l'application Android (lot 3, spec §5.2).

La page de la galerie charge ses vignettes et ses vidéos par des URL
relatives : une WebView n'y ajoute pas l'en-tête `Authorization`. Le
téléphone échange donc son jeton d'appareil (POST /galerie/session, par son
client épinglé) contre un identifiant de session court, qu'il pose en cookie.

- Le jeton durable ne quitte jamais le coffre chiffré du téléphone.
- On ne garde que l'EMPREINTE de l'identifiant, comme pour les jetons
  d'appareil : une copie de la mémoire du processus ne donne rien.
- En mémoire seulement : un redémarrage du service vide tout, la page reçoit
  401 et l'application refait l'échange sans que l'utilisateur le voie.
"""
import hashlib
import itertools
import secrets
import threading
import time

NOM_COOKIE = "phototheque_galerie"
DUREE_S = 12 * 3600
MAX_PAR_APPAREIL = 8


def _empreinte(valeur: str) -> str:
    return hashlib.sha256(valeur.encode()).hexdigest()


class SessionsGalerie:
    def __init__(self, duree_s: int = DUREE_S, max_par_appareil: int = MAX_PAR_APPAREIL,
                 horloge=time.monotonic) -> None:
        self._duree_s = duree_s
        self._max = max_par_appareil
        self._horloge = horloge
        # empreinte -> (appareil, expiration, ordre de création)
        self._sessions: dict[str, tuple[str, float, int]] = {}
        self._ordre = itertools.count()
        self._lock = threading.Lock()

    def _purger_expirees(self, maintenant: float) -> None:
        for e in [e for e, (_, exp, _) in self._sessions.items() if exp <= maintenant]:
            del self._sessions[e]

    def ouvrir(self, appareil: str) -> str:
        """Nouvelle session pour cet appareil ; rend la valeur à poser en cookie."""
        valeur = secrets.token_urlsafe(32)
        with self._lock:
            maintenant = self._horloge()
            self._purger_expirees(maintenant)
            siennes = sorted((o, e) for e, (a, _, o) in self._sessions.items() if a == appareil)
            # Un téléphone qui rouvre l'onglet cent fois ne remplit pas la
            # mémoire : au-delà du plafond, la plus ancienne tombe.
            while len(siennes) >= self._max:
                _, plus_vieille = siennes.pop(0)
                del self._sessions[plus_vieille]
            self._sessions[_empreinte(valeur)] = (
                appareil, maintenant + self._duree_s, next(self._ordre))
        return valeur

    def appareil(self, valeur: str | None) -> str | None:
        """L'appareil de cette session, ou None (inconnue, vide, expirée)."""
        if not valeur:
            return None
        e = _empreinte(valeur)
        with self._lock:
            ligne = self._sessions.get(e)
            if ligne is None:
                return None
            appareil, expiration, _ = ligne
            if expiration <= self._horloge():
                del self._sessions[e]
                return None
            return appareil

    def fermer_appareil(self, appareil: str) -> int:
        """Retire toutes les sessions de cet appareil (révocation, désappairage)."""
        with self._lock:
            siennes = [e for e, (a, _, _) in self._sessions.items() if a == appareil]
            for e in siennes:
                del self._sessions[e]
        return len(siennes)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/test_galerie_sessions.py`
Expected: PASS (9 tests).

- [ ] **Step 5: Validate by mutation**

`exp <= maintenant` → `exp < 0` dans `appareil` (expiration jamais vue) → `test_une_session_expire` tombe. Remplacer `while len(siennes) >= self._max` par `if False:` → `test_au_dela_du_plafond…` tombe. Remettre.

- [ ] **Step 6: Commit**

```bash
git add phototheque/galerie_sessions.py tests/test_galerie_sessions.py
git commit -F - <<'FIN'
feat(serveur): magasin de sessions de galerie en memoire

Identifiant de 256 bits dont seule l'empreinte est gardee, 12 h de
vie, au plus 8 sessions par appareil, purge par appareil pour la
revocation. Prepare l'onglet WebView de l'application (lot 3).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 6: Serveur — l'échange et le cookie dans `require_lecteur`

**Files:**
- Modify: `phototheque/app.py` (imports ~l.23 ; `require_lecteur` l.343-351 ; nouvelle route ; `sync_desappairer` l.688-708 ; `revoke_device` l.735-740 ; `galerie` l.860-877 ; `galerie_media` l.880-888)
- Test: `tests/test_galerie_routes.py` (ajouts en fin de fichier)

**Interfaces:**
- Consumes: `SessionsGalerie`, `NOM_COOKIE`, `DUREE_S` (tâche 5).
- Produces: `POST /galerie/session` → `{"cookie": "phototheque_galerie", "valeur": str, "expire_dans_s": 43200}` ; `@dataclass(frozen=True) class Lecteur: nature: str; appareil: str | None = None` ; `require_lecteur(...) -> Lecteur`. La tâche 7 lit `lecteur.nature == "appareil"`.

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `tests/test_galerie_routes.py` :

```python
# --- sessions de galerie (lot 3 de l'application, spec §5) ------------------

NOM = "phototheque_galerie"


def _session(a, client):
    """Appaire un téléphone et échange son jeton : (id, jeton, valeur du cookie)."""
    dev_id, jeton = a.devices().pair("Téléphone")
    r = client.post("/galerie/session", headers={"Authorization": f"Bearer {jeton}"})
    assert r.status_code == 200
    corps = r.json()
    assert corps["cookie"] == NOM and corps["expire_dans_s"] == 43200
    return dev_id, jeton, corps["valeur"]


def test_l_echange_exige_un_jeton_d_appareil(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    assert client.post("/galerie/session").status_code == 401
    assert client.post("/galerie/session", headers={"Authorization": "Bearer faux"}).status_code == 401
    # Le mot de passe d'administration ne suffit pas : l'échange est
    # réservé à un appareil.
    assert client.post("/galerie/session", headers=adm).status_code == 401


@pytest.mark.parametrize("adresse", ["/", "/?annee=2023", f"/galerie/media/{E_PHOTO}",
                                     f"/galerie/vignette/{E_PHOTO}",
                                     f"/galerie/moyenne/{E_PHOTO}",
                                     f"/galerie/original/{E_PHOTO}"])
def test_le_cookie_ouvre_la_galerie(adresse, tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    from phototheque import galerie_index
    galerie_index.vider_cache()
    _, _, valeur = _session(a, client)
    r = client.get(adresse, headers={"Cookie": f"{NOM}={valeur}"}, follow_redirects=False)
    assert r.status_code in (200, 307), (adresse, r.status_code)


def test_le_cookie_ouvre_une_video_en_lecture_partielle(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    _, _, valeur = _session(a, client)
    r = client.get(f"/galerie/original/{E_VIDEO}",
                   headers={"Cookie": f"{NOM}={valeur}", "Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100


@pytest.mark.parametrize("methode,adresse", [
    ("get", "/admin"), ("get", "/pair"), ("get", "/apk"), ("get", "/devices"),
    ("get", "/historique"), ("get", "/evenements"), ("get", "/status"),
    ("get", "/sync/horizon"), ("post", "/sync/plan"), ("post", "/sync/desappairer"),
    ("post", "/sync/abandon"), ("post", "/galerie/session"),
])
def test_le_cookie_n_ouvre_rien_d_autre_que_la_galerie(methode, adresse, tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    _, _, valeur = _session(a, client)
    extra = {"json": {}} if methode == "post" else {}
    r = getattr(client, methode)(adresse, headers={"Cookie": f"{NOM}={valeur}"}, **extra)
    # FastAPI résout les dépendances (l'authentification) avant de valider le
    # corps : un corps vide donne bien 401 ici, pas 422. Si un 422 apparaît,
    # c'est que la route n'exige plus d'authentification : à examiner.
    assert r.status_code == 401, (adresse, r.status_code)


def test_un_cookie_forge_est_refuse_sans_demander_de_mot_de_passe(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    r = client.get("/", headers={"Cookie": f"{NOM}=forge"})
    assert r.status_code == 401
    # Un défi Basic ferait ouvrir à la WebView une fenêtre de mot de passe.
    assert "www-authenticate" not in {k.lower() for k in r.headers}


def test_sans_cookie_ni_identifiants_le_navigateur_garde_son_defi_basic(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    r = client.get("/")
    assert r.status_code == 401 and "Basic" in r.headers.get("www-authenticate", "")


def test_les_identifiants_priment_sur_un_cookie(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    from phototheque import galerie_index
    galerie_index.vider_cache()
    r = client.get("/", headers={**adm, "Cookie": f"{NOM}=forge"})
    assert r.status_code == 200


def test_une_revocation_ferme_aussitot_la_galerie(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    dev_id, _, valeur = _session(a, client)
    assert client.post(f"/devices/{dev_id}/revoke", headers=adm).status_code == 200
    assert client.get(f"/galerie/vignette/{E_PHOTO}",
                      headers={"Cookie": f"{NOM}={valeur}"}).status_code == 401


def test_un_desappairage_ferme_aussitot_la_galerie(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    _, jeton, valeur = _session(a, client)
    assert client.post("/sync/desappairer",
                       headers={"Authorization": f"Bearer {jeton}"}).status_code == 200
    assert client.get(f"/galerie/vignette/{E_PHOTO}",
                      headers={"Cookie": f"{NOM}={valeur}"}).status_code == 401


def test_un_appareil_supprime_hors_revocation_n_ouvre_plus_la_galerie(tmp_path, monkeypatch):
    # Filet : même si la purge des sessions était oubliée quelque part,
    # chaque requête revérifie que l'appareil existe encore.
    a, client, _ = _client(tmp_path, monkeypatch)
    dev_id, _, valeur = _session(a, client)
    a.devices().revoke(dev_id)                  # directement, sans passer par la route
    assert client.get(f"/galerie/vignette/{E_PHOTO}",
                      headers={"Cookie": f"{NOM}={valeur}"}).status_code == 401


def test_un_redemarrage_du_service_invalide_les_sessions(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    _, _, valeur = _session(a, client)
    # Rechargement du module seul (les variables d'environnement posées par
    # _client restent) : c'est ce que fait un redémarrage du service.
    a2 = importlib.reload(a)
    client2 = TestClient(a2.app)
    assert client2.get(f"/galerie/vignette/{E_PHOTO}",
                       headers={"Cookie": f"{NOM}={valeur}"}).status_code == 401


def test_la_documentation_automatique_reste_fermee_apres_l_ajout_de_la_route(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    for chemin in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(chemin, headers=adm).status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest -q tests/test_galerie_routes.py -k "cookie or echange or revocation or desappairage or redemarrage or supprime or identifiants_priment or defi_basic or documentation"`
Expected: FAIL — `/galerie/session` répond 404/405, le cookie n'ouvre rien.

- [ ] **Step 3: Implement**

`phototheque/app.py` :

- imports : ajouter `from dataclasses import dataclass` en tête, et `galerie_sessions` dans la liste `from . import (...)`.
- après `_cache_auth = adminauth.CacheVerifications()` :

```python
# Sessions de la galerie pour l'application (lot 3, spec §5) : EN MÉMOIRE,
# un redémarrage les vide (l'application refait l'échange sur le 401).
_sessions_galerie = galerie_sessions.SessionsGalerie()
```

- remplacer `require_lecteur` :

```python
@dataclass(frozen=True)
class Lecteur:
    """Qui lit la galerie : « admin » (mot de passe) ou « appareil » (jeton ou
    cookie de session). Les pages en déduisent ce qu'elles montrent : un
    téléphone n'a ni l'administration ni le téléchargement (spec §5.2)."""
    nature: str
    appareil: str | None = None


def require_lecteur(request: Request, authorization: str = Header(default="")) -> Lecteur:
    """Lecture de la galerie : l'administrateur (mot de passe) OU un
    téléphone appairé — par son jeton, ou par le cookie de session obtenu en
    échange de ce jeton (POST /galerie/session). C'est la SEULE dépendance
    qui accepte ce cookie : ni require_admin ni require_device ne le lisent.

    Un en-tête Authorization prime toujours sur le cookie.
    """
    if authorization.startswith("Bearer "):
        return Lecteur("appareil", require_device(request, authorization))
    cookie = request.cookies.get(galerie_sessions.NOM_COOKIE)
    if cookie and not authorization:
        appareil = _sessions_galerie.appareil(cookie)
        # Revérifié à CHAQUE requête : une révocation ferme la galerie à la
        # requête suivante, même si une purge de sessions était oubliée.
        if appareil and devices().label(appareil) is not None:
            return Lecteur("appareil", appareil)
        # Pas de WWW-Authenticate: Basic ici : la WebView ouvrirait une
        # fenêtre de mot de passe. L'application traite ce 401 (spec §6).
        raise HTTPException(status_code=401, detail="session de galerie invalide")
    require_admin(request, authorization)
    return Lecteur("admin")
```

- nouvelle route, juste avant `@app.get("/", response_class=HTMLResponse)` :

```python
@app.post("/galerie/session")
def galerie_session(dev_id: str = Depends(require_device)) -> dict:
    """Échange le jeton d'appareil contre un cookie de session de galerie
    (lot 3 de l'application, docs/CONTRAT-APP.md §4.7). Le cookie est posé
    par l'application elle-même, avec ses attributs : le serveur ne renvoie
    que la valeur."""
    return {"cookie": galerie_sessions.NOM_COOKIE,
            "valeur": _sessions_galerie.ouvrir(dev_id),
            "expire_dans_s": galerie_sessions.DUREE_S}
```

- `sync_desappairer`, après `resultat = devices().revoke(dev_id)` : `_sessions_galerie.fermer_appareil(dev_id)`.
- `revoke_device`, après `resultat = devices().revoke(device_id)` : `_sessions_galerie.fermer_appareil(device_id)`.
- `galerie` et `galerie_media` : remplacer `_: None = Depends(require_lecteur)` par `lecteur: Lecteur = Depends(require_lecteur)` (la tâche 7 s'en sert ; pour l'instant la variable est inutilisée). Les routes `vignette`, `original`, `moyenne` gardent `_: Lecteur = Depends(require_lecteur)` (changer seulement l'annotation `None` → `Lecteur`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest -q`
Expected: PASS, suite complète verte (les tests existants de la galerie aussi).

- [ ] **Step 5: Validate by mutation**

Retirer `and devices().label(appareil) is not None` → `test_un_appareil_supprime_hors_revocation…` tombe. Retirer `_sessions_galerie.fermer_appareil(device_id)` **et** remettre la vérification → les tests de révocation passent encore (filet) : c'est attendu, noter dans le rapport que la purge est une défense en profondeur. Remplacer `if cookie and not authorization` par `if cookie` → `test_les_identifiants_priment_sur_un_cookie` tombe. Faire accepter le cookie par `require_device` (lire `request.cookies` dedans) → `test_le_cookie_n_ouvre_rien_d_autre…` tombe sur `/status`. Remettre.

- [ ] **Step 6: Commit**

```bash
git add phototheque/app.py tests/test_galerie_routes.py
git commit -F - <<'FIN'
feat(serveur): echange du jeton contre un cookie de galerie (lot 3 de l'app)

POST /galerie/session (require_device) ouvre une session de 12 h ;
require_lecteur est la seule dependance qui accepte le cookie, revoit
l'existence de l'appareil a chaque requete et dit qui lit. Revocation
et desappairage purgent les sessions. Un cookie refuse ne declenche
pas de defi Basic.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 7: Serveur — liens masqués pour un appareil, et le contrat

**Files:**
- Modify: `phototheque/web.py:680-793` (`galerie_html`, `media_html`, `_lecteur_video`)
- Modify: `phototheque/app.py` (`galerie`, `galerie_media`)
- Modify: `docs/CONTRAT-APP.md` (§4 : nouveau §4.7 ; §7 ; §9)
- Test: `tests/test_galerie_routes.py`

**Interfaces:**
- Consumes: `Lecteur` (tâche 6).
- Produces: `galerie_html(vue, pour_appareil: bool = False)`, `media_html(empreinte, nom, type_, taille, retour, pour_appareil: bool = False)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_un_telephone_ne_voit_ni_l_administration_ni_le_telechargement(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    from phototheque import galerie_index
    galerie_index.vider_cache()
    _, _, valeur = _session(a, client)
    h = {"Cookie": f"{NOM}={valeur}"}
    assert 'href="/admin"' not in client.get("/", headers=h).text
    photo = client.get(f"/galerie/media/{E_PHOTO}", headers=h).text
    video = client.get(f"/galerie/media/{E_VIDEO}", headers=h).text
    assert "download" not in photo and "download" not in video
    assert "ouvrez-la depuis un ordinateur" in video


def test_le_jeton_seul_donne_aussi_la_vue_telephone(tmp_path, monkeypatch):
    a, client, _ = _client(tmp_path, monkeypatch)
    from phototheque import galerie_index
    galerie_index.vider_cache()
    _, jeton = a.devices().pair("Téléphone")
    r = client.get("/", headers={"Authorization": f"Bearer {jeton}"})
    assert 'href="/admin"' not in r.text


def test_l_administrateur_garde_ses_deux_liens(tmp_path, monkeypatch):
    a, client, adm = _client(tmp_path, monkeypatch)
    from phototheque import galerie_index
    galerie_index.vider_cache()
    assert 'href="/admin"' in client.get("/", headers=adm).text
    assert "download" in client.get(f"/galerie/media/{E_PHOTO}", headers=adm).text
    assert "download" in client.get(f"/galerie/media/{E_VIDEO}", headers=adm).text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest -q tests/test_galerie_routes.py -k "telephone or deux_liens"`
Expected: FAIL — `href="/admin"` présent pour le téléphone.

- [ ] **Step 3: Implement**

`web.py`, `galerie_html(vue, pour_appareil: bool = False)` — remplacer la construction de l'en-tête :

```python
    # Un téléphone n'a pas le mot de passe : le lien mènerait à une demande
    # d'identifiants que la WebView refuse (lot 3 de l'application, spec §5.2).
    admin = "" if pour_appareil else ' · <a href="/admin">Administration</a>'
    corps = (
        f'<header><h1>{html.escape(vue.titre)}</h1>'
        f'<p class="hote">{_nombre(vue.total)} média(s){admin}</p></header>'
        f'<nav class="fil">{fil}</nav>{formulaire}{message}{blocs}{grille}{pages}')
```

`media_html(empreinte, nom, type_, taille, retour, pour_appareil: bool = False)` :

```python
    nom_sur = html.escape(nom)
    if type_ == "video":
        return _lecteur_video(empreinte, nom_sur, taille, retour, pour_appareil)
    # Pas de téléchargement dans l'application : une WebView ignore
    # `<a download>`, et DownloadManager ne connaîtrait ni le certificat
    # épinglé ni le cookie de session.
    telechargement = "" if pour_appareil else (
        f'<p class="indice"><a download href="/galerie/original/{empreinte}">'
        "Télécharger l'original</a></p>")
    contenu = f'<img src="/galerie/moyenne/{empreinte}" alt="{nom_sur}">{telechargement}'
```
(le reste de la fonction inchangé).

`_lecteur_video(empreinte, nom_sur, taille, retour, pour_appareil: bool = False)` :

```python
    if pour_appareil:
        # Le NUC ne transcode pas : si le téléphone ne sait pas lire ce
        # format, il n'y a rien à faire ici. On le dit, plutôt qu'un lien
        # inerte.
        secours = '<span class="nom">Si la vidéo ne démarre pas, ouvrez-la depuis un ordinateur</span>'
    else:
        secours = (f'<a download href="/galerie/original/{empreinte}" '
                   'title="Si la vidéo ne se lance pas, ce navigateur ne sait pas lire son format">'
                   "Télécharger</a>")
    corps = (
        '<div class="lecteur">'
        '<div class="barre">'
        f'<a href="{html.escape(retour)}">‹ Retour</a>'
        f'<span class="nom">{nom_sur} · {_go(taille)}</span>'
        f'{secours}</div>'
        f'<video controls autoplay playsinline preload="auto" '
        f'src="/galerie/original/{empreinte}"></video>'
        "</div>" + _SCRIPT_LECTURE)
```

Remarque : le libellé retenu (« Si la vidéo ne démarre pas, ouvrez-la depuis un ordinateur ») précise celui de la spec §5.2 : le serveur ne peut pas savoir à l'avance qu'un format est illisible sur le téléphone.

`app.py` : dans `galerie`, `return web.galerie_html(vue, pour_appareil=lecteur.nature == "appareil")` ; dans `galerie_media`, `return web.media_html(empreinte, p.name, type_, p.stat().st_size, retour, pour_appareil=lecteur.nature == "appareil")`.

`docs/CONTRAT-APP.md` :
- après le §4.6, ajouter :

````markdown
### 4.7 `POST /galerie/session` — ouvrir la galerie dans l'application (lot 3)

La page de la galerie charge vignettes et vidéos par des URL relatives, que
la `WebView` envoie **sans** l'en-tête `Authorization`. L'application échange
donc son jeton contre un cookie de session, par son client **épinglé** :

```
POST /galerie/session
Authorization: Bearer <jeton>
```

```json
{"cookie": "phototheque_galerie", "valeur": "<43 caractères base64url>", "expire_dans_s": 43200}
```

L'application pose elle-même le cookie dans le `CookieManager` de la
`WebView`, pour l'origine du serveur :
`phototheque_galerie=<valeur>; Path=/; Secure; HttpOnly; SameSite=Strict`
(sans `Secure` si le serveur n'a pas de TLS, en développement).

- Le cookie **n'ouvre que la galerie** (`/`, `/galerie/media`,
  `/galerie/vignette`, `/galerie/moyenne`, `/galerie/original`). Il est
  ignoré partout ailleurs, `/sync/*` et `/status` compris.
- Durée : 12 h, en mémoire ; un redémarrage du service les efface toutes.
  Au plus 8 sessions vivantes par appareil.
- Une révocation ou un désappairage ferme aussitôt les sessions de
  l'appareil.
- Un cookie refusé reçoit `401` **sans** `WWW-Authenticate: Basic`.
- Vue par un appareil, la galerie n'a ni lien « Administration » ni
  téléchargement.
````
- §7 (codes de retour) : ajouter une ligne pour `401` sur une page de la galerie portant le cookie → « session expirée, service redémarré ou appareil révoqué : refaire l'échange une fois ; un `401` de l'échange lui-même = révocation ».
- §9 (ce qui n'existe pas) : retirer toute mention d'un accès de l'application à la galerie s'il y en a une ; ajouter « aucun téléchargement d'original depuis l'application ».

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest -q`
Expected: PASS, suite complète verte (dont `test_l_accueil_est_la_galerie_et_liste_les_annees`, qui vérifie `href="/admin"` pour l'admin).

- [ ] **Step 5: Validate by mutation**

Passer `pour_appareil=False` en dur dans `galerie` → `test_un_telephone_ne_voit…` tombe. Remettre.

- [ ] **Step 6: Commit**

```bash
git add phototheque/web.py phototheque/app.py tests/test_galerie_routes.py docs/CONTRAT-APP.md
git commit -F - <<'FIN'
feat(serveur): la galerie vue par un telephone n'a ni administration ni telechargement

Les deux liens menaient a une demande de mot de passe ou a un
telechargement inerte dans une WebView. Contrat de l'echange de
session documente (CONTRAT-APP.md 4.7).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 8: App — l'échange de session (`ClientServeur`, `Fabrique.trouver`)

**Files:**
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Contrat.kt` (après `ChargeAppairage`)
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/ClientServeur.kt:43-45` (`baseUrl` public), fin de classe (nouvel appel)
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Decouverte.kt:132-153` (`Fabrique.serveur`)
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/reseau/ClientServeurTest.kt`

**Interfaces:**
- Produces: `@Serializable data class SessionGalerie(val cookie: String, val valeur: String, @SerialName("expire_dans_s") val expireDansS: Long)` ; `ClientServeur.baseUrl: String` (public) ; `fun ClientServeur.sessionGalerie(): SessionGalerie` (lève `ServeurRevoqueException` sur 401, `IOException` sinon) ; `fun Fabrique.trouver(context: Context, charge: ChargeAppairage): ClientServeur?`.

- [ ] **Step 1: Write the failing tests**

Ajouter à `ClientServeurTest` :

```kotlin
    @Test fun la_session_de_galerie_est_demandee_en_post_avec_le_jeton() {
        serveur.enqueue(MockResponse().setBody(
            """{"cookie":"phototheque_galerie","valeur":"abc-DEF_123","expire_dans_s":43200}"""))
        val s = client.sessionGalerie()
        assertEquals(SessionGalerie("phototheque_galerie", "abc-DEF_123", 43200), s)
        val requete = serveur.takeRequest()
        assertEquals("POST", requete.method)
        assertEquals("/galerie/session", requete.path)
        assertEquals("Bearer jeton-de-test", requete.getHeader("Authorization"))
    }

    @Test fun un_refus_de_la_session_de_galerie_signale_la_revocation() {
        serveur.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"jeton invalide"}"""))
        try {
            client.sessionGalerie()
            fail("un 401 doit lever ServeurRevoqueException")
        } catch (e: ServeurRevoqueException) {
            // attendu : seul un 401 de l'échange prouve la révocation
        }
    }

    @Test fun une_panne_du_serveur_n_est_pas_une_revocation() {
        serveur.enqueue(MockResponse().setResponseCode(500))
        try {
            client.sessionGalerie()
            fail("un 500 doit lever une IOException")
        } catch (e: ServeurRevoqueException) {
            fail("un 500 n'est pas une révocation")
        } catch (e: java.io.IOException) {
            // attendu
        }
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests 'fr.izquierdo.phototheque.reseau.ClientServeurTest'`
Expected: FAIL à la compilation (`sessionGalerie`, `SessionGalerie` inconnus).

- [ ] **Step 3: Implement**

`Contrat.kt` :

```kotlin
/** Réponse de POST /galerie/session (docs/CONTRAT-APP.md §4.7). L'application
 *  pose elle-même le cookie, avec ses attributs (galerie.CookieGalerie). */
@Serializable
data class SessionGalerie(
    val cookie: String,
    val valeur: String,
    @SerialName("expire_dans_s") val expireDansS: Long,
)
```

`ClientServeur.kt` : `private val baseUrl: String,` devient `val baseUrl: String,` (la galerie charge cette origine dans sa `WebView`). En fin de classe :

```kotlin
    /**
     * Échange le jeton contre un cookie de session de galerie (lot 3).
     * Client COURT : l'utilisateur attend, l'onglet affiche « Recherche du
     * serveur… ». Un 401 lève ServeurRevoqueException : c'est le seul
     * indice de révocation que la galerie tient pour sûr (spec §6).
     */
    fun sessionGalerie(): SessionGalerie =
        httpCourt.newCall(requete("/galerie/session").post("".toRequestBody()).build())
            .execute().use { r ->
                verifierCode(r, "session de galerie refusée")
                Contrat.json.decodeFromString(r.body!!.string())
            }
```

`Decouverte.kt`, `Fabrique` — scinder `serveur` :

```kotlin
    /**
     * Cherche le serveur : d'abord les adresses annoncées en mDNS, puis l'url
     * du QR en secours. Renvoie le client de la PREMIÈRE adresse qui répond,
     * ou null si rien ne répond — ce qui veut simplement dire « pas à la
     * maison », et n'est PAS une panne. La galerie s'en sert pour connaître
     * l'origine à charger ; la synchro, par [serveur].
     *
     * Lève [ServeurRevoqueException] si un serveur a RÉPONDU et nous refuse.
     */
    fun trouver(context: Context, charge: ChargeAppairage): ClientServeur? {
        // (corps actuel de `serveur`, à l'identique, sauf :
        //  `return Adaptateur(candidat)` devient `return candidat`)
    }

    fun serveur(context: Context, charge: ChargeAppairage): Serveur? =
        trouver(context, charge)?.let { Adaptateur(it) }
```
Déplacer les commentaires existants de la boucle avec elle ; ne rien changer d'autre.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest`
Expected: PASS, suite complète verte (`FabriqueTest` compris).

- [ ] **Step 5: Validate by mutation**

Retirer `verifierCode(...)` de `sessionGalerie` → `un_refus_de_la_session…` tombe (erreur de désérialisation au lieu de la révocation). Remettre.

- [ ] **Step 6: Commit**

```bash
git add android/app/src
git commit -F - <<'FIN'
feat(app): echange du jeton contre une session de galerie

ClientServeur.sessionGalerie (401 = revocation, le reste = panne
reseau) et Fabrique.trouver, qui rend le client de l'adresse qui a
repondu pour que la galerie en connaisse l'origine.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 9: App — les décisions pures de la `WebView`

**Files:**
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Epinglage.kt` (`empreinteDer`)
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/galerie/EpinglageWebView.kt`, `.../galerie/CookieGalerie.kt`, `.../galerie/Confinement.kt`, `.../galerie/SuiviChargement.kt`, `.../galerie/CheminGalerie.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/galerie/EpinglageWebViewTest.kt`, `CookieGalerieTest.kt`, `ConfinementTest.kt`, `SuiviChargementTest.kt`, `CheminGalerieTest.kt`

**Interfaces:**
- Consumes: `SessionGalerie` (tâche 8), `Epinglage` (existant).
- Produces:
  - `Epinglage.empreinteDer(der: ByteArray): String`
  - `object EpinglageWebView { fun accepte(der: ByteArray?, attendue: String?): Boolean }`
  - `object CookieGalerie { fun chaine(s: SessionGalerie, tls: Boolean): String }` (lève `IllegalArgumentException` sur une valeur ou un nom hors `[A-Za-z0-9_-]+`)
  - `object Confinement { fun autorise(url: String, origine: String): Boolean }`
  - `class SuiviChargement { fun debut(); fun erreur(); fun fin(): Boolean }` — `fin()` vrai seulement pour une navigation sans erreur
  - `object CheminGalerie { fun aCharger(origine: String, chemin: String?): String; fun cheminDe(url: String?): String? }`

- [ ] **Step 1: Write the failing tests**

`galerie/EpinglageWebViewTest.kt` :

```kotlin
package fr.izquierdo.phototheque.galerie

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate

/**
 * La WebView refuse le certificat auto-signé du NUC ; on n'accepte QUE celui
 * dont l'empreinte est dans le QR (spec §5.3).
 *
 * L'empreinte attendue est calculée HORS de l'application, par
 * `openssl x509 -outform der | sha256sum` sur le certificat ci-dessous
 * (le même que EpinglageTest) : un test qui la calculerait avec la fonction
 * testée ne pourrait rien voir.
 */
class EpinglageWebViewTest {
    private val certPem = """
        -----BEGIN CERTIFICATE-----
        MIIDEzCCAfugAwIBAgIUU6CHIm2nOAncyKzHvT9BUKCDrygwDQYJKoZIhvcNAQEL
        BQAwGTEXMBUGA1UEAwwOdGVzdC1lcGluZ2xhZ2UwHhcNMjYwOTE4MTcwNTU5WhcN
        MzYwOTE1MTcwNTU5WjAZMRcwFQYDVQQDDA50ZXN0LWVwaW5nbGFnZTCCASIwDQYJ
        KoZIhvcNAQEBBQADggEPADCCAQoCggEBAJ5FrxihKGXget1dEUZdwM4Fq7mPO3S1
        s9+ZJjOEzfUPntPkb2vt1KuVGd+OEY5FXSfUohwF2yLWWiaRYhHKS/jImDP0ZwNU
        XaJGmBa9Ns4r1f2yFeF3SKYoJWoaSZkuDnS1B9cCNiqArEe+/gyDKsIis2iAceE4
        2gizpkhiITWYQ5jpiev+hp0jsvgC3X9BfihvayV1TWA4KibmJ+Ng3GR+Sgwn4Xhj
        NdTYGX+swpuLZUxb21LQJhlE8XLWgnav2pAWTkogCvKnGSEJ5TkInf8W4d7eHKRg
        gnGwPn00yFqMHoP4e+UT0djZYFL4jhMKJaQz69YpLJqLP2YpWa1qKFECAwEAAaNT
        MFEwHQYDVR0OBBYEFHIWEMSXQM1X5yyY+jq6lx4EfQEdMB8GA1UdIwQYMBaAFHIW
        EMSXQM1X5yyY+jq6lx4EfQEdMA8GA1UdEwEB/wQFMAMBAf8wDQYJKoZIhvcNAQEL
        BQADggEBAAKUC/M/5m+KWzQT5dVgjUpySFSILB3m5982Ht6TwORpcfX4HtITtV6v
        4TGrkRgrq1xR5edg5c9Z2/fp9+FpCiFHOUJIFIu/V5epkHazN6IzmJprwJ2YYFP7
        1nyhAAfolYQtkMV0cMIrWFtHR/5rQPnPZuRs7zZk0fCMq0xBh40kOVxiSrk1csUO
        nfsB0PkobEaqtXs6aaMFgEzCIsvEDj928s3p44gI17VIv/uLwpC+6t67lBmRXeMV
        Yd74Acq3whlZkKYkX6CS49503HbKHxtVjetfGXx70VnVU03N4aQUNj5kRrYUz9x3
        vO6+9uEPAnZjx1YbczaUb/uEprxGAfY=
        -----END CERTIFICATE-----
    """.trimIndent()

    private val EMPREINTE_OPENSSL = "7fe1e5231fbc13a675a09c33ec3feeae15aaeb9d4989ffdd98be2710a740512b"

    private fun der(): ByteArray =
        (CertificateFactory.getInstance("X.509")
            .generateCertificate(certPem.byteInputStream()) as X509Certificate).encoded

    @Test fun le_certificat_du_qr_est_accepte() {
        assertTrue(EpinglageWebView.accepte(der(), EMPREINTE_OPENSSL))
    }

    @Test fun la_casse_et_les_espaces_du_qr_sont_sans_importance() {
        assertTrue(EpinglageWebView.accepte(der(), "  ${EMPREINTE_OPENSSL.uppercase()} \n"))
    }

    @Test fun un_autre_certificat_est_refuse() {
        assertFalse(EpinglageWebView.accepte(der(), "00".repeat(32)))
        // Une seule différence, au dernier caractère.
        assertFalse(EpinglageWebView.accepte(der(), EMPREINTE_OPENSSL.dropLast(1) + "c"))
    }

    @Test fun sans_certificat_ou_sans_empreinte_rien_n_est_accepte() {
        assertFalse(EpinglageWebView.accepte(null, EMPREINTE_OPENSSL))
        // Serveur appairé sans TLS : une erreur de certificat ne doit jamais
        // être acceptée « faute de mieux ».
        assertFalse(EpinglageWebView.accepte(der(), null))
        assertFalse(EpinglageWebView.accepte(der(), ""))
    }
}
```
(Le PEM est celui de `EpinglageTest.kt` ; l'empreinte ci-dessus a été calculée le 25/09 par `openssl x509 -outform der | sha256sum` sur ce PEM.)

`galerie/CookieGalerieTest.kt` :

```kotlin
package fr.izquierdo.phototheque.galerie

import fr.izquierdo.phototheque.reseau.SessionGalerie
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

class CookieGalerieTest {
    private val s = SessionGalerie("phototheque_galerie", "abc-DEF_123", 43200)

    @Test fun le_cookie_est_de_session_et_verrouille() {
        assertEquals("phototheque_galerie=abc-DEF_123; Path=/; Secure; HttpOnly; SameSite=Strict",
            CookieGalerie.chaine(s, tls = true))
    }

    @Test fun sans_tls_le_cookie_n_est_pas_secure() {
        // Sinon la WebView ne l'enverrait jamais au serveur HTTP de développement.
        assertEquals("phototheque_galerie=abc-DEF_123; Path=/; HttpOnly; SameSite=Strict",
            CookieGalerie.chaine(s, tls = false))
    }

    @Test fun une_valeur_hostile_ne_peut_pas_injecter_d_attribut() {
        for (v in listOf("a; Domain=evil", "a b", "a\nb", "", "a=b")) {
            try {
                CookieGalerie.chaine(s.copy(valeur = v), tls = true)
                fail("valeur acceptée : ${v.replace("\n", "\\n")}")
            } catch (e: IllegalArgumentException) { /* attendu */ }
        }
        try {
            CookieGalerie.chaine(s.copy(cookie = "x; Path=/"), tls = true)
            fail("nom de cookie hostile accepté")
        } catch (e: IllegalArgumentException) { /* attendu */ }
    }
}
```

`galerie/ConfinementTest.kt` :

```kotlin
package fr.izquierdo.phototheque.galerie

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ConfinementTest {
    private val o = "https://192.168.1.31:8787"

    @Test fun les_pages_de_la_galerie_sont_autorisees() {
        assertTrue(Confinement.autorise("$o/", o))
        assertTrue(Confinement.autorise("$o/?annee=2023&mois=6", o))
        assertTrue(Confinement.autorise("$o/galerie/media/${"a".repeat(64)}", o))
    }

    @Test fun un_autre_hote_un_autre_port_ou_un_autre_schema_sont_bloques() {
        assertFalse(Confinement.autorise("https://exemple.org/", o))
        assertFalse(Confinement.autorise("https://192.168.1.31:8788/", o))
        assertFalse(Confinement.autorise("http://192.168.1.31:8787/", o))
        assertFalse(Confinement.autorise("https://192.168.1.310:8787/", o))
        assertFalse(Confinement.autorise("https://192.168.1.31:8787@exemple.org/", o))
    }

    @Test fun une_url_illisible_est_bloquee() {
        assertFalse(Confinement.autorise("pas une url", o))
        assertFalse(Confinement.autorise("javascript:alert(1)", o))
        assertFalse(Confinement.autorise("file:///sdcard/", o))
    }

    @Test fun une_origine_ipv6_fonctionne() {
        // La découverte mDNS rend des adresses IPv6 entre crochets.
        val v6 = "https://[fe80::1]:8787"
        assertTrue(Confinement.autorise("$v6/?annee=2023", v6))
        assertFalse(Confinement.autorise("https://[fe80::2]:8787/", v6))
    }

    @Test fun le_nom_d_hote_est_insensible_a_la_casse_et_le_port_par_defaut_compte() {
        assertTrue(Confinement.autorise("https://IZQUIERDO-NUC.local:8787/", "https://izquierdo-nuc.local:8787"))
        assertTrue(Confinement.autorise("https://nuc.local:443/", "https://nuc.local"))
    }
}
```

`galerie/SuiviChargementTest.kt` :

```kotlin
package fr.izquierdo.phototheque.galerie

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * `onPageFinished` est appelé AUSSI après une page en erreur. Le traiter comme
 * « page chargée » remettrait à zéro le compteur de 401 de EtatGalerie, et la
 * WebView rééchangerait sans fin contre un serveur qui refuse.
 */
class SuiviChargementTest {
    @Test fun une_navigation_sans_erreur_est_chargee() {
        val s = SuiviChargement(); s.debut()
        assertTrue(s.fin())
    }

    @Test fun une_navigation_en_erreur_n_est_pas_chargee() {
        val s = SuiviChargement(); s.debut(); s.erreur()
        assertFalse(s.fin())
    }

    @Test fun l_erreur_est_oubliee_a_la_navigation_suivante() {
        val s = SuiviChargement(); s.debut(); s.erreur(); s.fin()
        s.debut()
        assertTrue(s.fin())
    }

    @Test fun une_erreur_signalee_apres_le_debut_mais_avant_la_fin_compte() {
        // Ordre réel sur un 401 : onPageStarted, onReceivedHttpError, onPageFinished.
        val s = SuiviChargement(); s.debut(); s.erreur(); s.erreur()
        assertFalse(s.fin())
    }
}
```

`galerie/CheminGalerieTest.kt` :

```kotlin
package fr.izquierdo.phototheque.galerie

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class CheminGalerieTest {
    @Test fun sans_chemin_on_ouvre_l_accueil_de_la_galerie() {
        assertEquals("https://192.168.1.31:8787/", CheminGalerie.aCharger("https://192.168.1.31:8787", null))
    }

    @Test fun le_chemin_retenu_est_recolle_a_la_nouvelle_origine() {
        // Le NUC a changé d'adresse entre deux ouvertures (.21 puis .31) :
        // on ne recharge JAMAIS l'ancienne.
        val chemin = CheminGalerie.cheminDe("https://192.168.1.21:8787/?annee=2023&mois=6")
        assertEquals("/?annee=2023&mois=6", chemin)
        assertEquals("https://192.168.1.31:8787/?annee=2023&mois=6",
            CheminGalerie.aCharger("https://192.168.1.31:8787", chemin))
    }

    @Test fun un_chemin_qui_n_est_pas_un_chemin_retombe_sur_l_accueil() {
        for (mauvais in listOf("//exemple.org/", "exemple.org/", "https://exemple.org/", "")) {
            assertEquals("https://nuc:8787/", CheminGalerie.aCharger("https://nuc:8787", mauvais))
        }
    }

    @Test fun une_url_illisible_ne_donne_aucun_chemin() {
        assertNull(CheminGalerie.cheminDe(null))
        assertNull(CheminGalerie.cheminDe("pas une url"))
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests 'fr.izquierdo.phototheque.galerie.*'`
Expected: FAIL à la compilation (paquet `galerie` vide).

- [ ] **Step 3: Implement**

`reseau/Epinglage.kt` :

```kotlin
object Epinglage {

    /** SHA-256 du certificat au format DER, en hexadécimal minuscule. */
    fun empreinte(certificat: X509Certificate): String = empreinteDer(certificat.encoded)

    /** Idem, depuis l'encodage DER directement : la WebView ne rend pas un
     *  X509Certificate de la même façon que OkHttp. */
    fun empreinteDer(der: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(der).joinToString("") { "%02x".format(it) }
}
```

`galerie/EpinglageWebView.kt` :

```kotlin
package fr.izquierdo.phototheque.galerie

import fr.izquierdo.phototheque.reseau.Epinglage
import java.security.MessageDigest

/**
 * Décision de `onReceivedSslError` (spec §5.3) : le même épinglage que le
 * client OkHttp (reseau.GestionnaireEpingle), appliqué à la WebView.
 * L'erreur de nom d'hôte (on vise une IP) n'est pas regardée : c'est
 * l'empreinte qui fait foi. Aucune autre issue que « celle-là, ou rien ».
 */
object EpinglageWebView {
    fun accepte(der: ByteArray?, attendue: String?): Boolean {
        if (der == null) return false
        val a = attendue?.trim()?.lowercase()
        if (a.isNullOrEmpty()) return false
        val obtenue = Epinglage.empreinteDer(der)
        return MessageDigest.isEqual(obtenue.toByteArray(), a.toByteArray())
    }
}
```

`galerie/CookieGalerie.kt` :

```kotlin
package fr.izquierdo.phototheque.galerie

import fr.izquierdo.phototheque.reseau.SessionGalerie

/**
 * La chaîne à passer à `CookieManager.setCookie` (spec §5.1). Cookie de
 * SESSION (sans Max-Age), HttpOnly (aucun script de la page ne le lit),
 * SameSite=Strict, et Secure dès que le serveur a TLS.
 *
 * Le nom et la valeur viennent du réseau : on refuse tout ce qui n'est pas
 * `[A-Za-z0-9_-]+`, sans quoi un « ; Domain=… » glissé dans la réponse
 * ajouterait un attribut. Le serveur légitime (secrets.token_urlsafe) n'émet
 * que ces caractères.
 */
object CookieGalerie {
    private val SUR = Regex("[A-Za-z0-9_-]+")

    fun chaine(s: SessionGalerie, tls: Boolean): String {
        require(SUR.matches(s.cookie)) { "nom de cookie inattendu" }
        require(SUR.matches(s.valeur)) { "valeur de cookie inattendue" }
        val secure = if (tls) "; Secure" else ""
        return "${s.cookie}=${s.valeur}; Path=/$secure; HttpOnly; SameSite=Strict"
    }
}
```

`galerie/Confinement.kt` :

```kotlin
package fr.izquierdo.phototheque.galerie

import java.net.URI

/**
 * La WebView ne quitte jamais le serveur trouvé (spec §5.4) : même schéma,
 * même hôte, même port. Tout le reste est bloqué dans
 * `shouldOverrideUrlLoading`, y compris une URL illisible.
 */
object Confinement {
    fun autorise(url: String, origine: String): Boolean {
        val u = lire(url) ?: return false
        val o = lire(origine) ?: return false
        if (u.userInfo != null) return false
        return u.scheme.equals(o.scheme, ignoreCase = true) &&
            u.host.equals(o.host, ignoreCase = true) &&
            port(u) == port(o)
    }

    private fun lire(texte: String): URI? = try {
        URI(texte).takeIf { it.scheme != null && it.host != null }
    } catch (e: Exception) {
        null
    }

    private fun port(u: URI): Int = when {
        u.port != -1 -> u.port
        u.scheme.equals("https", ignoreCase = true) -> 443
        u.scheme.equals("http", ignoreCase = true) -> 80
        else -> -1
    }
}
```

`galerie/SuiviChargement.kt` :

```kotlin
package fr.izquierdo.phototheque.galerie

/**
 * Distingue une page réellement chargée d'une page en erreur.
 *
 * `onPageFinished` est appelé dans les deux cas. Sans ce suivi, un 401 sur la
 * page principale serait suivi d'un « chargée » qui effacerait le compteur de
 * 401 de EtatGalerie — et la WebView rééchangerait sans fin (Review Focus 1).
 *
 * Appels attendus, dans l'ordre de la WebView : [debut] (onPageStarted),
 * [erreur] (onReceivedError / onReceivedHttpError de la page principale),
 * [fin] (onPageFinished).
 */
class SuiviChargement {
    private var enErreur = false

    fun debut() {
        enErreur = false
    }

    fun erreur() {
        enErreur = true
    }

    /** Vrai si la navigation qui se termine n'a connu aucune erreur. */
    fun fin(): Boolean = !enErreur
}
```

`galerie/CheminGalerie.kt` :

```kotlin
package fr.izquierdo.phototheque.galerie

import java.net.URI

/**
 * Ce que la galerie recharge après une rotation ou un nouvel échange.
 *
 * On retient le CHEMIN (avec sa requête), jamais l'URL complète : l'adresse
 * du NUC change (.21 puis .31 en deux jours), et recharger l'ancienne
 * origine mènerait à « pas à la maison » à trois mètres du serveur.
 */
object CheminGalerie {
    fun cheminDe(url: String?): String? {
        if (url == null) return null
        val u = try { URI(url) } catch (e: Exception) { return null }
        if (u.scheme == null || u.host == null) return null
        val chemin = u.rawPath?.ifEmpty { "/" } ?: "/"
        return if (u.rawQuery != null) "$chemin?${u.rawQuery}" else chemin
    }

    fun aCharger(origine: String, chemin: String?): String {
        // Un vrai chemin commence par UN « / » ; « //hote/ » serait lu par la
        // WebView comme une autre origine.
        val sur = chemin?.takeIf { it.startsWith("/") && !it.startsWith("//") } ?: "/"
        return origine.trimEnd('/') + sur
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest`
Expected: PASS, suite complète verte (`EpinglageTest` compris : `empreinte` délègue désormais à `empreinteDer`).

- [ ] **Step 5: Validate by mutation**

- `accepte` : renvoyer `true` quand `attendue` est vide → `sans_certificat_ou_sans_empreinte…` tombe.
- `CookieGalerie` : retirer le `require` de la valeur → `une_valeur_hostile…` tombe.
- `Confinement` : retirer la comparaison de port → `un_autre_hote_un_autre_port…` tombe ; retirer le test `userInfo` → la ligne `…:8787@exemple.org/` tombe (si `URI` en fait l'hôte `exemple.org`, la comparaison d'hôte suffit déjà : le noter).
- `SuiviChargement.debut` : ne plus remettre `enErreur` à faux → `l_erreur_est_oubliee…` tombe.
- `CheminGalerie.aCharger` : retirer `!it.startsWith("//")` → `un_chemin_qui_n_est_pas…` tombe.
Remettre chaque fois.

- [ ] **Step 6: Commit**

```bash
git add android/app/src
git commit -F - <<'FIN'
feat(app): decisions pures de la WebView de galerie

Epinglage par l'empreinte du QR (calculee hors application dans le
test), cookie de session verrouille et sans injection possible,
confinement a l'origine du serveur (IPv6 comprise), suivi qui ne prend
pas une page en erreur pour une page chargee, chemin recolle a la
nouvelle origine.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 10: App — la machine d'états `EtatGalerie`

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/galerie/EtatGalerie.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/galerie/EtatGalerieTest.kt`

**Interfaces:**
- Produces:
  - `enum class Phase { RECHERCHE, PAS_A_LA_MAISON, PRETE, REVOQUE }`
  - `sealed interface Evenement` avec `Introuvable`, `data class Session(val origine: String)`, `EchecReseau`, `Revoque`, `ErreurPage`, `CertificatRefuse`, `Page401`, `PageChargee`, `Reessayer` (objets `data object`)
  - `data class EtatGalerie(val phase: Phase = Phase.RECHERCHE, val origine: String? = null, val un401Deja: Boolean = false, val generation: Int = 0) { fun apres(e: Evenement): EtatGalerie; val doitEchanger: Boolean }`
  - `generation` augmente à chaque `Session` : la tâche 12 recharge la `WebView` quand elle change.

- [ ] **Step 1: Write the failing test**

```kotlin
package fr.izquierdo.phototheque.galerie

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Les états de l'onglet (spec §6). Jamais la page d'erreur du navigateur. */
class EtatGalerieTest {
    private val O = "https://192.168.1.31:8787"
    private fun prete() = EtatGalerie().apres(Evenement.Session(O))

    @Test fun l_onglet_commence_par_chercher_le_serveur() {
        assertEquals(Phase.RECHERCHE, EtatGalerie().phase)
        assertTrue(EtatGalerie().doitEchanger)
    }

    @Test fun un_echange_reussi_rend_la_galerie_prete_sur_son_origine() {
        val e = prete()
        assertEquals(Phase.PRETE, e.phase)
        assertEquals(O, e.origine)
        assertEquals(1, e.generation)
        assertFalse(e.doitEchanger)
    }

    @Test fun pas_de_serveur_ou_pas_de_reseau_donne_pas_a_la_maison() {
        for (ev in listOf(Evenement.Introuvable, Evenement.EchecReseau)) {
            assertEquals(Phase.PAS_A_LA_MAISON, EtatGalerie().apres(ev).phase)
        }
    }

    @Test fun une_erreur_de_la_page_ou_un_certificat_refuse_donnent_pas_a_la_maison() {
        for (ev in listOf(Evenement.ErreurPage, Evenement.CertificatRefuse)) {
            assertEquals(Phase.PAS_A_LA_MAISON, prete().apres(ev).phase)
        }
    }

    @Test fun reessayer_relance_la_recherche() {
        val e = EtatGalerie().apres(Evenement.Introuvable).apres(Evenement.Reessayer)
        assertEquals(Phase.RECHERCHE, e.phase)
        assertTrue(e.doitEchanger)
    }

    @Test fun un_premier_401_de_la_page_refait_l_echange_une_fois() {
        val e = prete().apres(Evenement.Page401)
        assertEquals(Phase.RECHERCHE, e.phase)
        assertTrue(e.un401Deja)
        val e2 = e.apres(Evenement.Session(O))
        assertEquals(Phase.PRETE, e2.phase)
        assertEquals(2, e2.generation)                 // la WebView recharge
    }

    @Test fun un_second_401_d_affilee_ne_boucle_pas() {
        val e = prete().apres(Evenement.Page401).apres(Evenement.Session(O)).apres(Evenement.Page401)
        assertEquals(Phase.PAS_A_LA_MAISON, e.phase)
        assertFalse(e.doitEchanger)
    }

    @Test fun une_page_chargee_entre_deux_401_remet_le_compteur_a_zero() {
        val e = prete().apres(Evenement.Page401).apres(Evenement.Session(O))
            .apres(Evenement.PageChargee).apres(Evenement.Page401)
        assertEquals(Phase.RECHERCHE, e.phase)         // un nouvel essai, pas l'abandon
    }

    @Test fun reessayer_oublie_le_401() {
        val e = prete().apres(Evenement.Page401).apres(Evenement.Session(O))
            .apres(Evenement.Page401).apres(Evenement.Reessayer)
        assertFalse(e.un401Deja)
    }

    @Test fun seul_un_refus_de_l_echange_est_une_revocation() {
        assertEquals(Phase.REVOQUE, EtatGalerie().apres(Evenement.Revoque).phase)
        // Un 401 de page ne vide jamais le coffre, même répété.
        val e = prete().apres(Evenement.Page401).apres(Evenement.Session(O)).apres(Evenement.Page401)
        assertTrue(e.phase != Phase.REVOQUE)
    }

    @Test fun une_revocation_est_definitive() {
        val r = EtatGalerie().apres(Evenement.Revoque)
        for (ev in listOf(Evenement.Reessayer, Evenement.Session(O), Evenement.Page401)) {
            assertEquals(Phase.REVOQUE, r.apres(ev).phase)
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests 'fr.izquierdo.phototheque.galerie.EtatGalerieTest'`
Expected: FAIL à la compilation.

- [ ] **Step 3: Implement**

```kotlin
package fr.izquierdo.phototheque.galerie

/** Ce que montre l'onglet Galerie (spec §6). */
enum class Phase {
    /** « Recherche du serveur… » : découverte puis échange en cours. */
    RECHERCHE,
    /** Le message de l'accueil + « Réessayer ». */
    PAS_A_LA_MAISON,
    /** La WebView. */
    PRETE,
    /** L'échange a répondu 401 : l'application revient à l'appairage. */
    REVOQUE,
}

sealed interface Evenement {
    /** La découverte n'a rien trouvé. */
    data object Introuvable : Evenement
    /** L'échange a réussi et le cookie est posé, pour cette origine. */
    data class Session(val origine: String) : Evenement
    /** L'échange a échoué pour une raison réseau (pas un 401). */
    data object EchecReseau : Evenement
    /** L'échange a répondu 401 : révocation prouvée par le jeton lui-même. */
    data object Revoque : Evenement
    /** La PAGE PRINCIPALE n'a pas pu se charger (réseau, 5xx). */
    data object ErreurPage : Evenement
    /** `onReceivedSslError` a refusé le certificat. */
    data object CertificatRefuse : Evenement
    /** La page principale a répondu 401 (session expirée, service redémarré). */
    data object Page401 : Evenement
    /** Une page principale s'est chargée SANS erreur (voir SuiviChargement). */
    data object PageChargee : Evenement
    /** L'utilisateur a appuyé sur « Réessayer ». */
    data object Reessayer : Evenement
}

/**
 * La machine d'états de l'onglet, pure et testée.
 *
 * Un 401 de la page refait l'échange UNE fois ; un second d'affilée mène à
 * « pas à la maison » sans boucler. Il ne vide jamais le coffre : seul un 401
 * de l'échange, authentifié par le jeton lui-même, prouve la révocation.
 */
data class EtatGalerie(
    val phase: Phase = Phase.RECHERCHE,
    val origine: String? = null,
    val un401Deja: Boolean = false,
    /** Augmente à chaque échange réussi : la WebView (re)charge quand il change. */
    val generation: Int = 0,
) {
    /** La découverte et l'échange doivent être lancés. */
    val doitEchanger: Boolean get() = phase == Phase.RECHERCHE

    fun apres(e: Evenement): EtatGalerie {
        if (phase == Phase.REVOQUE) return this
        return when (e) {
            Evenement.Introuvable, Evenement.EchecReseau,
            Evenement.ErreurPage, Evenement.CertificatRefuse ->
                copy(phase = Phase.PAS_A_LA_MAISON)
            is Evenement.Session ->
                copy(phase = Phase.PRETE, origine = e.origine, generation = generation + 1)
            Evenement.Revoque -> copy(phase = Phase.REVOQUE)
            Evenement.Page401 ->
                if (un401Deja) copy(phase = Phase.PAS_A_LA_MAISON, un401Deja = false)
                else copy(phase = Phase.RECHERCHE, un401Deja = true)
            Evenement.PageChargee -> copy(un401Deja = false)
            Evenement.Reessayer -> copy(phase = Phase.RECHERCHE, un401Deja = false)
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests 'fr.izquierdo.phototheque.galerie.EtatGalerieTest'`
Expected: PASS (11 tests).

- [ ] **Step 5: Validate by mutation**

`Page401` toujours vers `RECHERCHE` → `un_second_401_d_affilee_ne_boucle_pas` tombe. Retirer la garde `if (phase == Phase.REVOQUE)` → `une_revocation_est_definitive` tombe. Remettre.

- [ ] **Step 6: Commit**

```bash
git add android/app/src
git commit -F - <<'FIN'
feat(app): machine d'etats de l'onglet galerie

Recherche, pas a la maison, prete, revoque. Un 401 de page refait
l'echange une fois puis s'arrete ; seul un 401 de l'echange est une
revocation.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 11: App — la navigation avec l'onglet Galerie

**Files:**
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Navigation.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/NavigationTest.kt`

**Interfaces:**
- Produces: `Ecran.GALERIE` ; `Navigation.ecranAffiche` (règle ajoutée) ; `Navigation.retour(GALERIE) == ACCUEIL` ; `Navigation.avecBarre(ecran: Ecran): Boolean`.

- [ ] **Step 1: Write the failing tests**

Ajouter à `NavigationTest` :

```kotlin
    @Test fun une_synchro_ne_chasse_pas_l_utilisateur_de_la_galerie() {
        // La passe automatique démarre à la mise en charge : sans cette
        // règle, elle éjecterait l'utilisateur en pleine consultation.
        assertEquals(Ecran.GALERIE,
            Navigation.ecranAffiche(Ecran.GALERIE, appaire = true, synchroEnCours = true))
    }

    @Test fun la_galerie_n_est_pas_atteignable_sans_appairage() {
        assertEquals(Ecran.APPAIRAGE,
            Navigation.ecranAffiche(Ecran.GALERIE, appaire = false, synchroEnCours = true))
    }

    @Test fun le_retour_depuis_la_galerie_mene_a_l_accueil() {
        assertEquals(Ecran.ACCUEIL, Navigation.retour(Ecran.GALERIE))
    }

    @Test fun la_barre_d_onglets_n_apparait_que_sur_les_deux_onglets() {
        assertEquals(setOf(Ecran.ACCUEIL, Ecran.GALERIE),
            Ecran.values().filter { Navigation.avecBarre(it) }.toSet())
    }

    @Test fun perdre_l_appairage_depuis_la_galerie_ramene_a_l_accueil_au_reappairage() {
        assertEquals(Ecran.ACCUEIL, Navigation.demandeApres(Ecran.GALERIE, appaire = false))
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests 'fr.izquierdo.phototheque.ui.NavigationTest'`
Expected: FAIL à la compilation (`GALERIE` inconnu).

- [ ] **Step 3: Implement**

```kotlin
enum class Ecran { APPAIRAGE, ACCUEIL, GALERIE, DETAIL, REGLAGES, DOSSIERS, SAUVEGARDE, APPAREIL }
```

Dans `Navigation` :

```kotlin
    /**
     * L'écran réellement affiché, qui n'est pas toujours celui demandé.
     *
     * Sans appairage rien n'est atteignable. Une synchronisation en cours
     * ramène à l'accueil (son avancement doit rester visible)… sauf depuis la
     * galerie (lot 3) : la passe automatique démarre à la mise en charge, et
     * elle éjecterait l'utilisateur en pleine consultation. L'onglet
     * Sauvegarde, lui, montre l'avancement.
     */
    fun ecranAffiche(demande: Ecran, appaire: Boolean, synchroEnCours: Boolean): Ecran = when {
        !appaire -> Ecran.APPAIRAGE
        demande == Ecran.GALERIE -> Ecran.GALERIE
        synchroEnCours -> Ecran.ACCUEIL
        else -> demande
    }

    /** La barre d'onglets « Sauvegarde | Galerie » : sur ces deux écrans
     *  seulement. Les réglages sont des sous-écrans de Sauvegarde. */
    fun avecBarre(ecran: Ecran): Boolean = ecran == Ecran.ACCUEIL || ecran == Ecran.GALERIE

    fun retour(depuis: Ecran): Ecran? = when (depuis) {
        Ecran.APPAIRAGE, Ecran.ACCUEIL -> null
        Ecran.DETAIL, Ecran.REGLAGES, Ecran.GALERIE -> Ecran.ACCUEIL
        Ecran.DOSSIERS, Ecran.SAUVEGARDE, Ecran.APPAREIL -> Ecran.REGLAGES
    }
```
Mettre à jour la KDoc de l'objet (« à sept destinations » → « huit ») et celle de `retour` (le retour dans la galerie remonte d'abord l'historique de la page ; c'est `EcranGalerie` qui l'intercepte, tâche 12).

`MainActivity.kt` : ajouter une branche provisoire `Ecran.GALERIE -> {}` au `when (affiche)` pour que le `when` reste exhaustif (la tâche 12 la remplit).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest`
Expected: PASS, suite complète verte (dont `sans_appairage_aucun_autre_ecran_n_est_atteignable`, qui parcourt désormais `GALERIE` aussi).

- [ ] **Step 5: Validate by mutation**

Inverser les lignes `demande == Ecran.GALERIE` et `!appaire` → `la_galerie_n_est_pas_atteignable_sans_appairage` tombe. Retirer la ligne `demande == Ecran.GALERIE` → `une_synchro_ne_chasse_pas…` tombe. Remettre.

- [ ] **Step 6: Commit**

```bash
git add android/app/src
git commit -F - <<'FIN'
feat(app): destination Galerie dans la navigation

Une synchro en cours ne chasse pas l'utilisateur de la galerie, le
retour mene a l'accueil, la barre d'onglets n'apparait que sur les
deux onglets.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 12: App — assemblage : `WebView`, modèle, écran, barre d'onglets

Tâche Android pure : **aucun test JVM ne la couvre** (spec §9.1). Toutes les
décisions sont déjà dans les tâches 9 à 11 ; ce code ne fait que brancher.
Sa vérification est la compilation, les contrôles ci-dessous et la recette
(tâche 13).

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/galerie/VueGalerie.kt`
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/galerie/ModeleGalerie.kt`
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/EcranGalerie.kt`
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/BarreOnglets.kt`
- Create: `android/app/src/main/res/drawable/ic_onglet_sauvegarde.xml`, `android/app/src/main/res/drawable/ic_onglet_galerie.xml`
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/ModeleAccueil.kt` (nouvelle méthode ; `desappairer`, `effacerLocal`)
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/MainActivity.kt`

**Interfaces:**
- Consumes: `EtatGalerie`, `Evenement`, `Phase` (10) ; `EpinglageWebView`, `CookieGalerie`, `Confinement`, `SuiviChargement`, `CheminGalerie` (9) ; `Fabrique.trouver`, `ClientServeur.sessionGalerie`, `ClientServeur.baseUrl` (8) ; `Navigation.avecBarre`, `Ecran.GALERIE` (11) ; `Coffre` (existant) ; `Journal.info` (existant).
- Produces: `ModeleAccueil.constaterRevocation()`.

- [ ] **Step 1: Icons**

`res/drawable/ic_onglet_sauvegarde.xml` (pictogramme « cloud_upload » de Material Icons, licence Apache 2.0) :

```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24">
    <path android:fillColor="#FF000000"
        android:pathData="M19.35,10.04C18.67,6.59 15.64,4 12,4 9.11,4 6.6,5.64 5.35,8.04 2.34,8.36 0,10.91 0,14c0,3.31 2.69,6 6,6h13c2.76,0 5,-2.24 5,-5 0,-2.64 -2.05,-4.78 -4.65,-4.96zM14,13v4h-4v-4H7l5,-5 5,5h-3z"/>
</vector>
```

`res/drawable/ic_onglet_galerie.xml` (« photo_library », Material Icons, Apache 2.0) :

```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24">
    <path android:fillColor="#FF000000"
        android:pathData="M22,16V4c0,-1.1 -0.9,-2 -2,-2H8c-1.1,0 -2,0.9 -2,2v12c0,1.1 0.9,2 2,2h12c1.1,0 2,-0.9 2,-2zM11,12l2.03,2.71L16,11l4,5H8l3,-4zM2,6v14c0,1.1 0.9,2 2,2h14v-2H4V6H2z"/>
</vector>
```
(`Icon` les teinte avec la couleur de contenu : le noir de `fillColor` n'est jamais affiché tel quel.)

- [ ] **Step 2: `VueGalerie` — la WebView et ses clients**

```kotlin
package fr.izquierdo.phototheque.galerie

import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.ApplicationInfo
import android.graphics.Bitmap
import android.net.http.SslError
import android.view.View
import android.webkit.HttpAuthHandler
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import fr.izquierdo.phototheque.synchro.Journal

/**
 * La WebView de la galerie, créée UNE fois par activité (spec §7) : changer
 * d'onglet ne la recharge pas et garde le défilement.
 *
 * Aucune décision ici : elles sont toutes dans des fonctions pures testées
 * (EpinglageWebView, Confinement, SuiviChargement, CheminGalerie,
 * EtatGalerie). Ce fichier ne fait que les brancher sur les rappels de la
 * WebView — il n'est couvert que par la recette.
 */
@SuppressLint("SetJavaScriptEnabled")
class VueGalerie(
    context: Context,
    /** `cert_sha256` du QR ; null = serveur sans TLS (développement). */
    private val empreinte: String?,
    private val signaler: (Evenement) -> Unit,
) {
    val vue: WebView = WebView(context)

    /** L'origine chargée, fixée à chaque échange réussi (confinement). */
    var origine: String? = null

    /** Dernier chemin chargé sans erreur (rechargé après rotation ou 401). */
    var cheminCourant: String? = null

    /** Vrai si le bouton retour doit remonter l'historique de la page. */
    var peutRevenir by mutableStateOf(false)
        private set

    /** Vue plein écran d'une vidéo (`<video>`), ou null. */
    var pleinEcran by mutableStateOf<View?>(null)
        private set
    private var sortiePleinEcran: WebChromeClient.CustomViewCallback? = null

    private val suivi = SuiviChargement()

    init {
        vue.settings.apply {
            // Le seul script de la galerie est celui du lecteur vidéo.
            javaScriptEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            // Démarrage automatique de la vidéo (spec §7).
            mediaPlaybackRequiresUserGesture = false
            domStorageEnabled = false
        }
        // Débogage web (chrome://inspect) en APK de débogage seulement.
        // Pas de BuildConfig dans ce projet : on lit le drapeau du manifeste.
        WebView.setWebContentsDebuggingEnabled(
            (context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0)
        vue.webViewClient = Client()
        vue.webChromeClient = Chrome()
    }

    fun charger(url: String) = vue.loadUrl(url)

    /** Quitte le plein écran ; vrai s'il était actif. */
    fun quitterPleinEcran(): Boolean {
        val cb = sortiePleinEcran ?: return false
        cb.onCustomViewHidden()
        return true
    }

    fun revenir() = vue.goBack()

    fun detruire() = vue.destroy()

    private inner class Client : WebViewClient() {
        override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
            val der = error.certificate?.x509Certificate?.encoded
            if (EpinglageWebView.accepte(der, empreinte)) {
                handler.proceed()
            } else {
                handler.cancel()
                Journal.info("galerie : certificat refusé (empreinte différente du QR)")
                signaler(Evenement.CertificatRefuse)
            }
        }

        // Jamais de fenêtre de mot de passe : la WebView n'en a pas.
        override fun onReceivedHttpAuthRequest(view: WebView, handler: HttpAuthHandler,
                                               host: String, realm: String) = handler.cancel()

        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val o = origine ?: return true
            val autorise = Confinement.autorise(request.url.toString(), o)
            if (!autorise) Journal.info("galerie : navigation hors du serveur bloquée")
            return !autorise
        }

        override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) = suivi.debut()

        override fun onReceivedError(view: WebView, request: WebResourceRequest,
                                     error: WebResourceError) {
            if (!request.isForMainFrame) return          // une vignette : la page a son remplaçant
            suivi.erreur()
            Journal.info("galerie : la page n'a pas pu se charger (${error.errorCode})")
            signaler(Evenement.ErreurPage)
        }

        override fun onReceivedHttpError(view: WebView, request: WebResourceRequest,
                                         response: WebResourceResponse) {
            if (!request.isForMainFrame) return
            when {
                response.statusCode == 401 -> {
                    suivi.erreur()
                    Journal.info("galerie : 401 sur la page principale")
                    signaler(Evenement.Page401)
                }
                response.statusCode >= 500 -> {
                    suivi.erreur()
                    Journal.info("galerie : le serveur a répondu ${response.statusCode}")
                    signaler(Evenement.ErreurPage)
                }
                // 404 (média retiré du catalogue) : la page du serveur s'affiche.
            }
        }

        override fun onPageFinished(view: WebView, url: String?) {
            if (suivi.fin()) {
                cheminCourant = CheminGalerie.cheminDe(url) ?: cheminCourant
                signaler(Evenement.PageChargee)
            }
        }

        override fun doUpdateVisitedHistory(view: WebView, url: String?, isReload: Boolean) {
            peutRevenir = view.canGoBack()
        }
    }

    private inner class Chrome : WebChromeClient() {
        // Sans ces deux rappels, le bouton plein écran de <video> ne fait rien.
        override fun onShowCustomView(view: View, callback: CustomViewCallback) {
            pleinEcran = view
            sortiePleinEcran = callback
        }

        override fun onHideCustomView() {
            pleinEcran = null
            sortiePleinEcran = null
        }
    }
}
```

Remarque de journalisation : ne jamais écrire l'URL, l'hôte ni une empreinte de média (spec §7) — seulement la nature de l'événement.

- [ ] **Step 3: `ModeleGalerie` — découverte, échange, cookie**

```kotlin
package fr.izquierdo.phototheque.galerie

import android.app.Application
import android.webkit.CookieManager
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import fr.izquierdo.phototheque.appairage.Coffre
import fr.izquierdo.phototheque.reseau.Fabrique
import fr.izquierdo.phototheque.reseau.ServeurRevoqueException
import fr.izquierdo.phototheque.synchro.Journal
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlin.coroutines.resume

/**
 * Tient EtatGalerie et lance la découverte + l'échange chaque fois que la
 * machine le demande (`doitEchanger`). Aucune règle ici : elles sont dans
 * EtatGalerie.
 */
class ModeleGalerie(application: Application) : AndroidViewModel(application) {
    private val _etat = MutableStateFlow(EtatGalerie())
    val etat: StateFlow<EtatGalerie> = _etat.asStateFlow()
    private var echangeEnCours = false

    /** Appelé à la première ouverture de l'onglet, et par les rappels de la WebView. */
    fun signaler(e: Evenement) {
        _etat.value = _etat.value.apres(e)
        if (_etat.value.doitEchanger) echanger()
    }

    fun demarrer() {
        if (_etat.value.doitEchanger) echanger()
    }

    private fun echanger() {
        if (echangeEnCours) return
        echangeEnCours = true
        viewModelScope.launch {
            val issue = withContext(Dispatchers.IO) { tenterEchange() }
            echangeEnCours = false
            signaler(issue)
        }
    }

    private suspend fun tenterEchange(): Evenement {
        val charge = Coffre(getApplication()).charge() ?: return Evenement.Revoque
        return try {
            val client = Fabrique.trouver(getApplication(), charge)
                ?: return Evenement.Introuvable.also {
                    Journal.info("galerie : serveur introuvable sur le réseau (pas une panne)")
                }
            val session = client.sessionGalerie()
            poserCookie(client.baseUrl, CookieGalerie.chaine(session, tls = charge.certSha256 != null))
            Journal.info("galerie : session ouverte")
            Evenement.Session(client.baseUrl)
        } catch (e: ServeurRevoqueException) {
            Journal.info("galerie : échange refusé (401), appareil révoqué")
            Evenement.Revoque
        } catch (e: Exception) {
            Journal.info("galerie : échange impossible (${e.javaClass.simpleName})")
            Evenement.EchecReseau
        }
    }

    /**
     * Efface les cookies de session précédents PUIS pose le nouveau (spec §7) :
     * aucune session d'une exécution précédente ne traîne. Les deux appels
     * sont asynchrones ; on attend chacun avant de charger la page.
     */
    private suspend fun poserCookie(origine: String, chaine: String) = withContext(Dispatchers.Main) {
        val cm = CookieManager.getInstance()
        suspendCancellableCoroutine { c -> cm.removeSessionCookies { c.resume(Unit) } }
        suspendCancellableCoroutine { c -> cm.setCookie(origine, chaine) { c.resume(Unit) } }
        cm.flush()
    }
}
```

- [ ] **Step 4: `ModeleAccueil` — révocation vue par la galerie, cookies effacés**

Ajouter à `ModeleAccueil` :

```kotlin
    /**
     * La galerie a reçu un 401 de l'échange (spec §6) : même conséquence
     * qu'une révocation vue par la synchro — coffre vidé, retour à
     * l'appairage avec le bandeau « révoqué ».
     */
    fun constaterRevocation() {
        coffre.oublier()
        android.webkit.CookieManager.getInstance().removeAllCookies(null)
        _etat.value = _etat.value.copy(appaire = false, revoque = true)
    }
```
Dans `desappairer`, bloc `effacerLocal = { … }`, après `coffre.oublier()` : `android.webkit.CookieManager.getInstance().removeAllCookies(null)` — avec un commentaire : le cookie de galerie est déjà invalide côté serveur si celui-ci a été prévenu, mais pas s'il était injoignable.

Attention : `effacerLocal` tourne sur `Dispatchers.IO` ; `removeAllCookies` accepte d'être appelé hors du fil principal quand on ne lui passe pas de rappel. Si la recette montre une exception de fil, l'envelopper dans `withContext(Dispatchers.Main)`.

- [ ] **Step 5: `EcranGalerie` et `BarreOnglets`**

`ui/EcranGalerie.kt` :

```kotlin
package fr.izquierdo.phototheque.ui

import android.view.ViewGroup
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import fr.izquierdo.phototheque.galerie.CheminGalerie
import fr.izquierdo.phototheque.galerie.EtatGalerie
import fr.izquierdo.phototheque.galerie.Phase
import fr.izquierdo.phototheque.galerie.VueGalerie

/**
 * L'onglet Galerie : un état natif tant que la galerie n'est pas prête
 * (jamais la page d'erreur du navigateur), la WebView ensuite.
 *
 * @param cheminSauve chemin retenu à travers une rotation (rememberSaveable
 *        dans MainActivity) ; @param surChemin le met à jour.
 */
@Composable
fun EcranGalerie(etat: EtatGalerie, vue: VueGalerie, cheminSauve: String?,
                 surChemin: (String?) -> Unit, surReessayer: () -> Unit) {
    // Retour : d'abord le plein écran, puis l'historique de la page. Déclaré
    // ici, donc prioritaire sur celui de MainActivity (qui mène à l'accueil).
    BackHandler(enabled = vue.pleinEcran != null) { vue.quitterPleinEcran() }
    BackHandler(enabled = vue.pleinEcran == null && etat.phase == Phase.PRETE && vue.peutRevenir) {
        vue.revenir()
    }

    // Chaque échange réussi (generation) (re)charge la page : premier
    // affichage, ou rechargement après un 401. Le chemin est recollé à
    // l'origine du moment, jamais à l'ancienne adresse du NUC.
    LaunchedEffect(etat.generation) {
        val o = etat.origine ?: return@LaunchedEffect
        if (etat.phase != Phase.PRETE) return@LaunchedEffect
        vue.origine = o
        vue.charger(CheminGalerie.aCharger(o, vue.cheminCourant ?: cheminSauve))
    }
    LaunchedEffect(vue.cheminCourant) { surChemin(vue.cheminCourant) }

    when (etat.phase) {
        Phase.RECHERCHE -> Centre { CircularProgressIndicator(); Spacer(Modifier.height(16.dp)); Text("Recherche du serveur…") }
        Phase.PAS_A_LA_MAISON -> Centre {
            Text("Serveur introuvable — vous n'êtes probablement pas chez vous.")
            Spacer(Modifier.height(16.dp))
            Button(onClick = surReessayer) { Text("Réessayer") }
        }
        Phase.PRETE -> Box(Modifier.fillMaxSize()) {
            AndroidView(modifier = Modifier.fillMaxSize(), factory = {
                // La même WebView d'un onglet à l'autre : la détacher de son
                // ancien parent avant de la rattacher.
                vue.vue.also { (it.parent as? ViewGroup)?.removeView(it) }
            })
            vue.pleinEcran?.let { plein ->
                AndroidView(modifier = Modifier.fillMaxSize(), factory = {
                    plein.also { (it.parent as? ViewGroup)?.removeView(it) }
                })
            }
        }
        // MainActivity réagit (constaterRevocation) ; rien à montrer ici.
        Phase.REVOQUE -> Unit
    }
}

@Composable
private fun Centre(contenu: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp),
           verticalArrangement = Arrangement.Center,
           horizontalAlignment = Alignment.CenterHorizontally, content = contenu)
}
```

Remarque : `vue.cheminCourant` n'est pas un état Compose ; si `LaunchedEffect(vue.cheminCourant)` ne se redéclenche pas, rendre `cheminCourant` observable dans `VueGalerie` (`var cheminCourant by mutableStateOf<String?>(null)`), comme `peutRevenir`.

`ui/BarreOnglets.kt` :

```kotlin
package fr.izquierdo.phototheque.ui

import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.painterResource
import fr.izquierdo.phototheque.R

/** « Sauvegarde | Galerie » (spec §4). Ouverture sur Sauvegarde. */
@Composable
fun BarreOnglets(affiche: Ecran, surChoisir: (Ecran) -> Unit) {
    NavigationBar {
        NavigationBarItem(
            selected = affiche == Ecran.ACCUEIL, onClick = { surChoisir(Ecran.ACCUEIL) },
            icon = { Icon(painterResource(R.drawable.ic_onglet_sauvegarde), contentDescription = null) },
            label = { Text("Sauvegarde") })
        NavigationBarItem(
            selected = affiche == Ecran.GALERIE, onClick = { surChoisir(Ecran.GALERIE) },
            icon = { Icon(painterResource(R.drawable.ic_onglet_galerie), contentDescription = null) },
            label = { Text("Galerie") })
    }
}
```

- [ ] **Step 6: `MainActivity` — brancher**

- `private val modeleGalerie: ModeleGalerie by viewModels()` à côté de `modele`.
- Dans `setContent { ThemePhototheque { … } }`, après le calcul de `affiche` :

```kotlin
                val etatGalerie by modeleGalerie.etat.collectAsStateWithLifecycle()
                // Une seule WebView pour toute la vie de l'activité (spec §7).
                val charge = remember(etat.appaire) { Coffre(applicationContext).charge() }
                val vueGalerie = remember(charge?.certSha256) {
                    VueGalerie(this@MainActivity, charge?.certSha256, modeleGalerie::signaler)
                }
                DisposableEffect(vueGalerie) { onDispose { vueGalerie.detruire() } }
                // Retenu à travers une rotation ; la position dans la page est perdue (accepté).
                var cheminGalerie by rememberSaveable { mutableStateOf<String?>(null) }
                LaunchedEffect(affiche) { if (affiche == Ecran.GALERIE) modeleGalerie.demarrer() }
                LaunchedEffect(etatGalerie.phase) {
                    if (etatGalerie.phase == Phase.REVOQUE) modele.constaterRevocation()
                }
```
- Envelopper le `when (affiche)` dans un `Scaffold` :

```kotlin
                Scaffold(bottomBar = {
                    if (Navigation.avecBarre(affiche)) BarreOnglets(affiche) { demande = it }
                }) { marges ->
                    Box(Modifier.padding(marges)) {
                        when (affiche) {
                            // … branches existantes inchangées …
                            Ecran.GALERIE -> EcranGalerie(
                                etat = etatGalerie, vue = vueGalerie,
                                cheminSauve = cheminGalerie,
                                surChemin = { cheminGalerie = it },
                                surReessayer = { modeleGalerie.signaler(Evenement.Reessayer) })
                        }
                    }
                }
```
(imports : `Coffre`, `VueGalerie`, `ModeleGalerie`, `Evenement`, `Phase`, `BarreOnglets`, `EcranGalerie`, `Scaffold`, `Box`, `padding`, `Modifier`, `DisposableEffect`.)

Remarque sur `remember(charge?.certSha256)` : un réappairage sur un NUC dont le certificat a changé recrée la WebView avec la nouvelle empreinte ; l'ancienne est détruite par le `DisposableEffect`. Après une révocation, `modeleGalerie` garde `REVOQUE` (définitif) : au réappairage, le remettre à neuf — ajouter à `ModeleGalerie` une méthode `fun oublier() { _etat.value = EtatGalerie() }`, appelée depuis `MainActivity` par `LaunchedEffect(etat.appaire) { if (etat.appaire) modeleGalerie.oublier() }` **uniquement** si la phase courante est `REVOQUE`.

- [ ] **Step 7: Build and check**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest assembleDebug`
Expected: BUILD SUCCESSFUL, suite complète verte.
Contrôles :
- `grep -c foregroundServiceType android/app/build/intermediates/merged_manifests/debug/processDebugManifest/AndroidManifest.xml` → au moins 1 (rien de cassé côté service) ;
- `grep -c 'Theme.Phototheque' …/AndroidManifest.xml` (même fichier) → au moins 1 ;
- `grep -rn "addJavascriptInterface\|allowUniversalAccessFromFileURLs\|setAllowFileAccessFromFileURLs" android/app/src/main` → aucune ligne.

- [ ] **Step 8: Commit**

```bash
git add android/app/src
git commit -F - <<'FIN'
feat(app): onglet Galerie en WebView epinglee, barre d'onglets Sauvegarde | Galerie

La WebView n'accepte que le certificat du QR, ne quitte pas l'origine
du serveur, porte un cookie de session obtenu par echange du jeton, et
ne montre jamais la page d'erreur du navigateur. Une seule WebView par
activite, plein ecran video, retour dans l'historique de la page. Une
revocation vue par la galerie ramene a l'appairage.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```

---

### Task 13: Documentation — mode d'emploi, recette, point de reprise

**Files:**
- Modify: `docs/APPLICATION-ANDROID.md` (§8 : onglets ; §9 : recette du lot 3 à la fin du §9, avant `## 10.` ; §11 : galerie)
- Modify: `CLAUDE.md` (État actuel, REPRISE, Feuille de route, pièges)

- [ ] **Step 1: `APPLICATION-ANDROID.md`**

- **§8**, en tête : un paragraphe « **Deux onglets** : Sauvegarde (l'accueil, qui dit si tout est sauvegardé et fonctionne hors de la maison) et Galerie (la galerie du NUC, à la maison seulement). Les réglages restent sous Sauvegarde. Une synchro qui démarre pendant la consultation ne fait pas quitter la galerie. »
- **§9**, nouvelle sous-section `### Recette du lot 3 (thème, galerie, #42, #39)`, avec en préalable : relever d'abord l'étape 11 du lot 2 ; puis inventaire de `incoming/` et `./deploy/install.sh` sur le NUC (le serveur doit connaître `POST /galerie/session`) ; `./deploy/envoyer-apk.sh` puis installation (`adb install -r`, même clé : appairage conservé) ; `adb shell dumpsys package fr.izquierdo.phototheque | grep lastUpdateTime`. Puis les onze étapes de la spec §9.2, **recopiées** (numérotées 1 à 11, chacune avec ce qu'on fait et ce qu'on doit constater, et la commande de contrôle quand il y en a une : `journalctl -u phototheque --since "10 min ago" | grep galerie`, `adb logcat -s Phototheque`, `adb shell dumpsys jobscheduler | grep -A3 fr.izquierdo.phototheque`). L'étape 1 (la vidéo porte le cookie) est marquée « **à faire en premier** ».
- **§11**, nouvelle entrée `### La galerie affiche « Serveur introuvable » alors que la sauvegarde marche` : les causes possibles (NUC pas encore mis à jour → l'échange répond 404 et l'app le prend pour une panne réseau ; certificat changé → ligne `galerie : certificat refusé` ; deux 401 d'affilée → ligne `galerie : 401 …`) et la commande `adb logcat -s Phototheque | grep galerie`.

- [ ] **Step 2: `CLAUDE.md`**

- **État actuel** : une puce « ✅ **Lot 3 de l'app ÉCRIT** (spec `docs/superpowers/specs/2026-09-25-app-android-lot3-design.md`, plan `docs/superpowers/plans/2026-09-25-app-android-lot3.md`, branche `lot3-app-galerie`) : thème de l'admin (#43), onglet Galerie en `WebView` (cookie de session court `POST /galerie/session`, épinglage `onReceivedSslError`, états natifs), #42, #39. **Pas encore installé** ni sur le NUC ni sur le téléphone. » avec les nouveaux nombres de tests (les relever par `python3 -m pytest -q | tail -1` et le rapport Gradle, ne pas les inventer).
- **REPRISE** : après le relevé de l'étape 11, « installer le lot 3 (NUC d'abord : l'app a besoin de `POST /galerie/session`) et dérouler sa recette, `docs/APPLICATION-ANDROID.md` §9 ».
- **Pièges** (sous « Pièges de l'application Android ») :
  - « **Une `WebView` n'envoie l'en-tête `Authorization` qu'à la page chargée par `loadUrl`** : ni les `<img>`, ni la `<video>` en `Range`, ni un `307`, ni un lien. D'où le cookie de session (lot 3). »
  - « **Avec `targetSdk` ≥ 33, une `WebView` ne passe `prefers-color-scheme: dark` qu'à une activité au thème sombre** (`isLightTheme` faux) : c'est `res/values-night/themes.xml` qui le fait, pas Compose. »
  - « **`onPageFinished` est appelé aussi après une page en erreur** : ne jamais y voir une réussite sans `SuiviChargement`. »
- **Feuille de route** : #42 et #39 portent `Closes` (fermeture à la fusion dans `main`). #43 n'en porte pas (son critère d'acceptation est une comparaison sur le téléphone) : à fermer à la main après la recette.

- [ ] **Step 3: Final verification**

Run: `python3 -m pytest -q` → tout vert.
Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest assembleDebug` → BUILD SUCCESSFUL.
Relire les deux documents : aucun « TODO », aucune étape de recette sans ce qu'on doit constater.

- [ ] **Step 4: Commit**

```bash
git add docs/APPLICATION-ANDROID.md CLAUDE.md
git commit -F - <<'FIN'
docs: lot 3 de l'app - onglets, recette de la galerie et du theme, pieges WebView

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
FIN
```
