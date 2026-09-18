# Application Android — lot 1 : appairage, envoi manuel, écrans

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** scanner le QR du serveur, appuyer sur un bouton, et voir ses photos arriver rangées dans la bibliothèque du NUC.

**Architecture :** application Kotlin native. La logique qui peut perdre des photos (règle de l'horizon, conversion des dates) est du Kotlin pur, sans Android ni réseau, testée sur la JVM. Autour, des modules fins : lecture `MediaStore`, empreintes, client HTTP épinglé, et une interface Compose de trois écrans. Toute décision métier reste au serveur.

**Tech Stack :** Kotlin, Jetpack Compose, OkHttp, kotlinx.serialization, ZXing (QR), `NsdManager` (mDNS), `EncryptedSharedPreferences`, JUnit 5 + MockWebServer.

**Spec :** [`docs/superpowers/specs/2026-09-18-application-android-design.md`](../specs/2026-09-18-application-android-design.md)

**Contrat serveur :** [`docs/CONTRAT-APP.md`](../../CONTRAT-APP.md) — à lire avant la tâche 4.

## Global Constraints

- `minSdk 29`, `targetSdk 34`, JDK **17**.
- Le code vit dans **`android/`** à la racine de ce dépôt.
- **Documentation et commentaires en français** (convention du projet, `CLAUDE.md`).
- Messages de commit **sans accents**, comme tout le dépôt.
- `MANAGE_EXTERNAL_STORAGE` est **interdite**. Permissions : `READ_MEDIA_IMAGES` + `READ_MEDIA_VIDEO`.
- Aucun fichier n'est jamais lu entièrement en mémoire : toujours en flux.
- L'application ne supprime **jamais** rien sur le téléphone.
- Horizons envoyés au serveur : **secondes flottantes**.
- Pas d'émulateur : les essais se font sur le téléphone réel par USB.
- **Jamais `assert(...)` de Kotlin dans un test** : il dépend du drapeau `-ea` de
  la JVM et, s'il était désactivé, le test passerait sans rien vérifier.
  Toujours `assertTrue` / `assertEquals` de JUnit, qui vérifient inconditionnellement.
- **Ne jamais tester une représentation textuelle là où c'est une valeur qui
  compte.** Vérifier qu'un corps JSON *contient la chaîne* « 1789000000 » teste
  un détail de formatage : Kotlin sérialise ce nombre en `1.789E9`, notation
  scientifique parfaitement valide que le serveur relit correctement. Analyser
  le JSON et comparer la valeur, toujours.
- **Lancer un test ciblé :** `JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests '*XTest*'`.
  La tâche agrégée `test` éclate en variantes debug ET release, et le filtre
  `--tests` la fait alors échouer ; `testDebugUnitTest` est la bonne cible.
  Sans filtre, `./gradlew test` fonctionne normalement.

---

## Structure des fichiers

```
android/
  settings.gradle.kts
  build.gradle.kts
  gradle/libs.versions.toml
  app/
    build.gradle.kts
    src/main/AndroidManifest.xml
    src/main/kotlin/fr/izquierdo/phototheque/
      synchro/Dates.kt            # conversion des unités  (Kotlin pur)
      synchro/Horizons.kt         # règle de l'horizon      (Kotlin pur)
      synchro/Orchestrateur.kt    # enchaînement d'une synchro
      reseau/Contrat.kt           # modèles JSON du contrat
      reseau/Epinglage.kt         # X509TrustManager par empreinte
      reseau/ClientServeur.kt     # les quatre appels
      reseau/Decouverte.kt        # mDNS _phototheque._tcp
      medias/Depot.kt             # lecture MediaStore
      medias/Empreintes.kt        # SHA-256 en flux
      appairage/Appairage.kt      # QR + stockage chiffré
      ui/                         # Compose : appairage, accueil, detail
    src/test/kotlin/…             # tests JVM (rapides, sans Android)
```

Les deux fichiers de `synchro/` qui portent la logique critique (`Dates.kt`,
`Horizons.kt`) ne dépendent de **rien** : ni Android, ni réseau, ni base. C'est
délibéré et c'est ce qui rend leurs tests instantanés.

---

### Task 1 : Outillage et squelette qui compile

**Files:**
- Create: `android/settings.gradle.kts`, `android/build.gradle.kts`, `android/app/build.gradle.kts`, `android/gradle/libs.versions.toml`, `android/app/src/main/AndroidManifest.xml`
- Create: `android/app/src/test/kotlin/fr/izquierdo/phototheque/SqueletteTest.kt`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: rien
- Produces: un projet Gradle où `./gradlew test` tourne — toutes les tâches suivantes en dépendent.

- [ ] **Step 1 : Installer JDK 17 et le SDK Android, sans sudo**

```bash
mkdir -p ~/outils && cd ~/outils
# JDK 17 (Temurin), decompresse dans le dossier personnel : pas de sudo
curl -L -o jdk17.tar.gz https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse
tar xzf jdk17.tar.gz && mv jdk-17* jdk17 && rm jdk17.tar.gz
# Outils en ligne de commande du SDK Android
curl -L -o cmdtools.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
mkdir -p ~/outils/android-sdk/cmdline-tools && unzip -q cmdtools.zip -d /tmp/ct
mv /tmp/ct/cmdline-tools ~/outils/android-sdk/cmdline-tools/latest && rm cmdtools.zip
export JAVA_HOME=~/outils/jdk17 ANDROID_HOME=~/outils/android-sdk
yes | ~/outils/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses
~/outils/android-sdk/cmdline-tools/latest/bin/sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"
```

Vérifier : `~/outils/jdk17/bin/java -version` affiche 17, et `ls ~/outils/android-sdk/platforms` contient `android-34`.

- [ ] **Step 2 : Écrire le test qui échoue**

`android/app/src/test/kotlin/fr/izquierdo/phototheque/SqueletteTest.kt` :

```kotlin
package fr.izquierdo.phototheque

import org.junit.Assert.assertEquals
import org.junit.Test

/** Vérifie seulement que la chaîne de compilation et de test fonctionne. */
class SqueletteTest {
    @Test fun le_projet_compile_et_les_tests_tournent() {
        assertEquals(4, 2 + 2)
    }
}
```

- [ ] **Step 3 : Vérifier qu'il échoue**

Run: `cd android && ./gradlew test`
Expected: FAIL — il n'y a pas encore de projet Gradle (`gradlew` absent).

- [ ] **Step 4 : Créer le projet**

`android/settings.gradle.kts` :

```kotlin
pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositories { google(); mavenCentral() }
}
rootProject.name = "phototheque"
include(":app")
```

`android/build.gradle.kts` :

```kotlin
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.24" apply false
    id("org.jetbrains.kotlin.plugin.serialization") version "1.9.24" apply false
}
```

`android/app/build.gradle.kts` :

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "fr.izquierdo.phototheque"
    compileSdk = 34
    defaultConfig {
        applicationId = "fr.izquierdo.phototheque"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "0.1"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
    composeOptions { kotlinCompilerExtensionVersion = "1.5.14" }
    sourceSets["main"].java.srcDirs("src/main/kotlin")
    sourceSets["test"].java.srcDirs("src/test/kotlin")
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.0")
    implementation(platform("androidx.compose:compose-bom:2024.06.00"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.2")
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}
```

`android/app/src/main/AndroidManifest.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />
    <uses-permission android:name="android.permission.READ_MEDIA_VIDEO" />
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE"
        android:maxSdkVersion="32" />
    <uses-permission android:name="android.permission.CAMERA" />
    <application android:label="Photothèque" android:supportsRtl="true" />
</manifest>
```

Puis engendrer le wrapper. `sdkmanager` ne fournit pas Gradle : on le télécharge
une fois, uniquement pour qu'il crée le wrapper que le projet utilisera ensuite.

```bash
cd ~/outils
curl -L -o gradle.zip https://services.gradle.org/distributions/gradle-8.7-bin.zip
unzip -q gradle.zip && rm gradle.zip
cd ~/dev/phone_camera_import/android
JAVA_HOME=~/outils/jdk17 ~/outils/gradle-8.7/bin/gradle wrapper --gradle-version 8.7
```

Ajouter à `.gitignore` :

```
android/.gradle/
android/build/
android/app/build/
android/local.properties
```

Et créer `android/local.properties` (non versionné) :

```
sdk.dir=/home/invisart/outils/android-sdk
```

- [ ] **Step 5 : Vérifier que le test passe**

Run: `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew test`
Expected: PASS, 1 test.

- [ ] **Step 6 : Commit**

```bash
git add android .gitignore
git commit -m "chore(android): squelette Gradle du sous-projet 3, un test qui tourne"
```

---

### Task 2 : Conversion des dates — le piège à 1000×

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Dates.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/DatesTest.kt`

**Interfaces:**
- Consumes: rien (Kotlin pur)
- Produces: `Dates.instantSecondes(dateTakenMs: Long?, dateModifiedSecondes: Long): Double`

- [ ] **Step 1 : Écrire les tests qui échouent**

```kotlin
package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Trois unités pour la même notion : DATE_TAKEN en millisecondes (parfois
 * absent), DATE_MODIFIED en secondes, et le serveur qui attend des secondes
 * flottantes. Se tromper d'un facteur 1000 fait avancer un horizon de
 * trente ans et perd tout le dossier, définitivement et en silence.
 */
class DatesTest {

    @Test fun date_de_prise_de_vue_convertie_en_secondes() {
        // 2026-09-12 14:30:00 UTC = 1789223400 s = 1789223400000 ms
        assertEquals(1789223400.0, Dates.instantSecondes(1789223400000L, 0L), 0.001)
    }

    @Test fun date_de_prise_de_vue_absente_on_prend_la_date_de_modification() {
        assertEquals(1789223400.0, Dates.instantSecondes(null, 1789223400L), 0.001)
    }

    @Test fun date_de_prise_de_vue_a_zero_compte_comme_absente() {
        // MediaStore renvoie 0 et non null quand la métadonnée manque.
        assertEquals(1789223400.0, Dates.instantSecondes(0L, 1789223400L), 0.001)
    }

    @Test fun les_millisecondes_ne_sont_pas_perdues() {
        assertEquals(1789223400.5, Dates.instantSecondes(1789223400500L, 0L), 0.001)
    }
}
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*DatesTest*'`
Expected: FAIL — `Unresolved reference: Dates`

- [ ] **Step 3 : Implémenter**

```kotlin
package fr.izquierdo.phototheque.synchro

/**
 * Conversion des dates de MediaStore vers l'unité du serveur.
 *
 * C'est la SEULE fonction du projet autorisée à convertir une date de média.
 * Toute autre conversion ailleurs finirait par diverger de celle-ci.
 */
object Dates {

    /**
     * Instant du média en secondes flottantes, tel que l'attend le serveur.
     *
     * @param dateTakenMs      MediaStore.DATE_TAKEN, en MILLISECONDES.
     *                         Vaut null ou 0 quand la métadonnée manque, ce qui
     *                         est fréquent sur les vidéos et les images reçues.
     * @param dateModifiedSecondes MediaStore.DATE_MODIFIED, en SECONDES.
     */
    fun instantSecondes(dateTakenMs: Long?, dateModifiedSecondes: Long): Double =
        if (dateTakenMs != null && dateTakenMs > 0L) dateTakenMs / 1000.0
        else dateModifiedSecondes.toDouble()
}
```

- [ ] **Step 4 : Vérifier qu'ils passent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*DatesTest*'`
Expected: PASS, 4 tests.

- [ ] **Step 5 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Dates.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/DatesTest.kt
git commit -m "feat(android): conversion des dates MediaStore vers l'unite du serveur"
```

---

### Task 3 : La règle de l'horizon — le seul code qui peut perdre des photos

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Horizons.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/HorizonsTest.kt`

**Interfaces:**
- Consumes: rien (Kotlin pur)
- Produces: `enum class Issue { CONFIRME, IGNORE, ECHEC }`, `data class Envoi(val dossier: String, val instant: Double, val issue: Issue)`, `Horizons.calculer(envois: List<Envoi>): Map<String, Double>`

- [ ] **Step 1 : Écrire les tests qui échouent**

```kotlin
package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

/**
 * La règle de l'horizon, telle que la fixe docs/CONTRAT-APP.md §5 : c'est
 * l'APPLICATION qui décide, le serveur enregistre sans vérifier. Un horizon
 * avancé au-delà d'un fichier jamais reçu perd ce média définitivement et sans
 * le moindre signal.
 */
class HorizonsTest {

    @Test fun tout_reussit_l_horizon_vaut_le_dernier_fichier() {
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.CONFIRME),
        )
        assertEquals(mapOf("DCIM/Camera" to 200.0), Horizons.calculer(envois))
    }

    @Test fun un_echec_au_milieu_arrete_l_horizon_avant_lui() {
        // Le fichier a 300 REUSSIT, mais celui a 200 a echoue : retenir 300
        // ferait sauter l'horizon par-dessus 200, plus jamais propose.
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.ECHEC),
            Envoi("DCIM/Camera", 300.0, Issue.CONFIRME),
        )
        assertEquals(mapOf("DCIM/Camera" to 100.0), Horizons.calculer(envois))
    }

    @Test fun une_extension_refusee_ne_bloque_pas_l_horizon() {
        // 400 « extension non prise en charge » n'est PAS un echec : bloquer
        // dessus fermerait le dossier a jamais (contrat, section 6).
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.IGNORE),
            Envoi("DCIM/Camera", 300.0, Issue.CONFIRME),
        )
        assertEquals(mapOf("DCIM/Camera" to 300.0), Horizons.calculer(envois))
    }

    @Test fun le_premier_fichier_echoue_le_dossier_est_absent_du_resultat() {
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.ECHEC),
            Envoi("DCIM/Camera", 200.0, Issue.CONFIRME),
        )
        assertFalse("DCIM/Camera" in Horizons.calculer(envois))
    }

    @Test fun un_dossier_en_echec_n_affecte_pas_les_autres() {
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.ECHEC),
            Envoi("Pictures/WhatsApp", 150.0, Issue.CONFIRME),
        )
        assertEquals(mapOf("Pictures/WhatsApp" to 150.0), Horizons.calculer(envois))
    }

    @Test fun l_ordre_de_la_liste_n_influence_pas_le_resultat() {
        // La regle doit dependre des DATES, pas de l'ordre d'arrivee.
        val envois = listOf(
            Envoi("DCIM/Camera", 300.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.ECHEC),
        )
        assertEquals(mapOf("DCIM/Camera" to 100.0), Horizons.calculer(envois))
    }

    @Test fun une_extension_refusee_en_DERNIER_fait_quand_meme_avancer_l_horizon() {
        // Le cas que `une_extension_refusee_ne_bloque_pas_l_horizon` ne couvre
        // PAS : la-bas, un CONFIRME a 300 suit l'IGNORE et ecrase ce qu'il
        // aurait pose, si bien que le test passe que IGNORE fasse avancer
        // l'horizon ou qu'il soit purement saute. Ici, IGNORE est le dernier
        // evenement du dossier : c'est le seul cas ou la propriete est
        // observable.
        //
        // Enjeu reel : si IGNORE ne faisait pas avancer l'horizon, un dossier
        // dont le dernier fichier est refuse resterait fige juste avant lui ;
        // ce fichier serait repropose puis re-refuse a chaque synchro, et TOUS
        // les medias suivants du dossier ne seraient jamais sauvegardes. C'est
        // le blocage permanent que docs/CONTRAT-APP.md section 6 interdit.
        val envois = listOf(
            Envoi("DCIM/Camera", 100.0, Issue.CONFIRME),
            Envoi("DCIM/Camera", 200.0, Issue.IGNORE),
        )
        assertEquals(mapOf("DCIM/Camera" to 200.0), Horizons.calculer(envois))
    }

    @Test fun aucun_envoi_aucun_horizon() {
        assertEquals(emptyMap<String, Double>(), Horizons.calculer(emptyList()))
    }
}
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*HorizonsTest*'`
Expected: FAIL — `Unresolved reference: Horizons`

- [ ] **Step 3 : Implémenter**

```kotlin
package fr.izquierdo.phototheque.synchro

/** Ce qu'est devenu un envoi. */
enum class Issue {
    /** Le serveur a répondu 200 : le média est chez lui. */
    CONFIRME,

    /** Refusé (400, extension non prise en charge). Volontairement PAS un
     *  échec : bloquer l'horizon dessus fermerait le dossier à jamais. */
    IGNORE,

    /** Tout le reste : réseau coupé, 5xx, erreur de lecture locale. */
    ECHEC,
}

/** Un envoi tenté, avec la date du média concerné (secondes). */
data class Envoi(val dossier: String, val instant: Double, val issue: Issue)

object Horizons {

    /**
     * Horizon à transmettre pour chaque dossier : la date du dernier fichier
     * confirmé AVANT le premier échec de ce dossier.
     *
     * Pourquoi pas « la date la plus haute confirmée » : si le fichier n° 5
     * échoue et que le n° 6 réussit, retenir la plus haute ferait sauter
     * l'horizon par-dessus le n° 5, qui ne serait PLUS JAMAIS proposé par le
     * serveur — perte définitive et silencieuse.
     *
     * Un dossier dont le premier fichier échoue est absent du résultat : son
     * horizon ne doit pas bouger du tout.
     */
    fun calculer(envois: List<Envoi>): Map<String, Double> {
        val horizons = mutableMapOf<String, Double>()
        val arretes = mutableSetOf<String>()
        // Trié par date : c'est ce qui donne un sens à « le dernier confirmé ».
        for (envoi in envois.sortedBy { it.instant }) {
            if (envoi.dossier in arretes) continue
            when (envoi.issue) {
                Issue.ECHEC -> arretes += envoi.dossier
                Issue.CONFIRME, Issue.IGNORE -> horizons[envoi.dossier] = envoi.instant
            }
        }
        return horizons
    }
}
```

- [ ] **Step 4 : Vérifier qu'ils passent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*HorizonsTest*'`
Expected: PASS, 8 tests.

- [ ] **Step 5 : Valider par mutation**

Remplacer `if (envoi.dossier in arretes) continue` par `if (false) continue`, relancer :
Expected: `un_echec_au_milieu_arrete_l_horizon_avant_lui` ÉCHOUE. Restaurer ensuite.

Puis remplacer `Issue.CONFIRME, Issue.IGNORE ->` par `Issue.CONFIRME ->` (et ajouter `Issue.IGNORE -> {}`), relancer :
Expected: `une_extension_refusee_en_DERNIER_fait_quand_meme_avancer_l_horizon` ÉCHOUE.
Restaurer.

**Attention :** cette seconde mutation ne casse PAS
`une_extension_refusee_ne_bloque_pas_l_horizon`, où un `CONFIRME` postérieur
écrase de toute façon ce qu'`IGNORE` aurait posé. Ce test-là ne prouve que
« `IGNORE` ne bloque pas comme un `ECHEC` ». C'est le test « en DERNIER » qui
prouve « `IGNORE` fait avancer l'horizon ». Les deux sont nécessaires.

- [ ] **Step 6 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Horizons.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/HorizonsTest.kt
git commit -m "feat(android): regle de l'horizon, validee par mutation"
```

---

### Task 4 : Modèles JSON du contrat

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Contrat.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/reseau/ContratTest.kt`

**Interfaces:**
- Consumes: rien
- Produces: `ChargeAppairage(url, token, certSha256)`, `ReponseHorizon(depuis, dossiers)`, `FichierPlan(path, size, hash)`, `RequetePlan(files)`, `ReponsePlan(session, needed)`, `RequeteCommit(session, horizons)`, `ReponseUpload(ok, hash)`, `Contrat.json: Json`

**Lire d'abord :** `docs/CONTRAT-APP.md`. Les exemples ci-dessous en sont extraits mot pour mot — ils ont été capturés sur un échange réel avec le serveur.

- [ ] **Step 1 : Écrire les tests qui échouent**

```kotlin
package fr.izquierdo.phototheque.reseau

import kotlinx.serialization.decodeFromString
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Les charges utiles viennent de docs/CONTRAT-APP.md, capturees en vrai. */
class ContratTest {

    @Test fun charge_du_qr() {
        val brut = """
            {"url":"https://IZQUIERDO-NUC.local:8787",
             "token":"SLgiMxHinPOYVMZMEO_jEAYT9vQIbxkXMFfm5BgixTw",
             "cert_sha256":"02f00ed30b8e621f38681b89ae14dd69d4936b180a0bd88318344157cf3a05fb"}
        """.trimIndent()
        val charge = Contrat.json.decodeFromString<ChargeAppairage>(brut)
        assertEquals("https://IZQUIERDO-NUC.local:8787", charge.url)
        assertEquals(64, charge.certSha256!!.length)
    }

    @Test fun le_certificat_du_qr_peut_etre_absent() {
        // Serveur lance a la main en HTTP : pas d'epinglage possible.
        val charge = Contrat.json.decodeFromString<ChargeAppairage>(
            """{"url":"http://192.168.1.21:8787","token":"x","cert_sha256":null}""")
        assertNull(charge.certSha256)
    }

    @Test fun horizon_premiere_synchro() {
        val r = Contrat.json.decodeFromString<ReponseHorizon>(
            """{"depuis":"2026-09-01","dossiers":{}}""")
        assertEquals("2026-09-01", r.depuis)
        assertEquals(emptyMap<String, Double>(), r.dossiers)
    }

    @Test fun depuis_peut_valoir_null_ce_qui_signifie_aucune_limite() {
        val r = Contrat.json.decodeFromString<ReponseHorizon>(
            """{"depuis":null,"dossiers":{"DCIM/Camera":1789000000.0}}""")
        assertNull(r.depuis)
        assertEquals(1789000000.0, r.dossiers["DCIM/Camera"]!!, 0.001)
    }

    @Test fun reponse_du_plan_contient_des_empreintes_pas_des_chemins() {
        val r = Contrat.json.decodeFromString<ReponsePlan>(
            """{"session":"4bad0393fe5f4fd69635802c39699ce1",
                "needed":["c777d42e972fefb334f506835d77ad0ab12500b5a4db7fe29fe995faf8df80f7"]}""")
        assertEquals(32, r.session.length)
        assertEquals(64, r.needed.first().length)
    }

    @Test fun la_requete_du_plan_porte_les_trois_champs_obligatoires() {
        // path et size ne sont jamais lus par le serveur, mais les omettre
        // donne un 422 (verifie). Voir CONTRAT-APP.md section 4.2.
        val encode = Contrat.json.encodeToString(
            RequetePlan.serializer(),
            RequetePlan(listOf(FichierPlan("DCIM/a.jpg", 954L, "ab".repeat(32)))))
        assert(encode.contains("\"path\""))
        assert(encode.contains("\"size\""))
        assert(encode.contains("\"hash\""))
    }
}
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*ContratTest*'`
Expected: FAIL — `Unresolved reference: Contrat`

- [ ] **Step 3 : Implémenter**

```kotlin
package fr.izquierdo.phototheque.reseau

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * Modèles des échanges avec le serveur. Le contrat complet, avec des exemples
 * capturés sur un échange réel, est dans docs/CONTRAT-APP.md.
 */
object Contrat {
    /** ignoreUnknownKeys : le serveur peut enrichir ses réponses sans casser
     *  une version ancienne de l'application installée sur un téléphone. */
    val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
}

/** Les trois champs encodés dans le QR d'appairage, et pas un de plus. */
@Serializable
data class ChargeAppairage(
    val url: String,
    val token: String,
    /** SHA-256 du certificat en DER. `null` = serveur sans TLS, pas d'épinglage. */
    @SerialName("cert_sha256") val certSha256: String? = null,
)

/**
 * Réponse de GET /sync/horizon.
 *
 * ATTENTION, deux unités dans la même réponse : `depuis` est une DATE ISO,
 * les valeurs de `dossiers` sont des TIMESTAMPS UNIX en secondes.
 * `depuis` à null signifie « aucune limite », pas « rien à envoyer ».
 */
@Serializable
data class ReponseHorizon(val depuis: String?, val dossiers: Map<String, Double>)

/** `path` et `size` sont obligatoires (422 sinon) mais jamais lus : seul
 *  `hash` sert. Conservés pour un futur pré-filtre serveur (issue #22). */
@Serializable
data class FichierPlan(val path: String, val size: Long, val hash: String)

@Serializable
data class RequetePlan(val files: List<FichierPlan>)

/** `needed` contient des EMPREINTES, pas des chemins : c'est à l'application
 *  de refaire la correspondance. */
@Serializable
data class ReponsePlan(val session: String, val needed: List<String>)

@Serializable
data class ReponseUpload(val ok: Boolean, val hash: String)

@Serializable
data class RequeteCommit(val session: String, val horizons: Map<String, Double> = emptyMap())
```

- [ ] **Step 4 : Vérifier qu'ils passent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*ContratTest*'`
Expected: PASS, 6 tests.

- [ ] **Step 5 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Contrat.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/reseau/ContratTest.kt
git commit -m "feat(android): modeles JSON du contrat serveur"
```

---

### Task 5 : Épinglage du certificat

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Epinglage.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/reseau/EpinglageTest.kt`

**Interfaces:**
- Consumes: rien
- Produces: `Epinglage.empreinte(certificat: X509Certificate): String`, `class GestionnaireEpingle(empreinteAttendue: String) : X509TrustManager`

**Pourquoi pas `CertificatePinner` d'OkHttp :** il épingle la **clé publique**
(SPKI). Le QR transmet le SHA-256 du **certificat** (DER). Ce ne sont pas les
mêmes octets ; utiliser l'un pour l'autre ne marche pas.

- [ ] **Step 1 : Engendrer le certificat de test**

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=test-epinglage" \
    -keyout /dev/null -out /tmp/cert-test.pem 2>/dev/null
cat /tmp/cert-test.pem
```

Garder la sortie sous la main : elle est collée telle quelle dans le test de
l'étape suivante, entre les lignes `BEGIN` et `END` incluses.

- [ ] **Step 2 : Écrire les tests qui échouent**

```kotlin
package fr.izquierdo.phototheque.reseau

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate

class EpinglageTest {

    /** Certificat auto-signe engendre a l'etape 1, colle ici tel quel. Il n'a
     *  pas besoin d'etre secret : il ne sert qu'a verifier que l'epinglage
     *  accepte le bon certificat et refuse tous les autres. */
    private val certPem = """
        -----BEGIN CERTIFICATE-----
        MIIC... (sortie complete de l'etape 1, lignes BEGIN et END incluses)
        -----END CERTIFICATE-----
    """.trimIndent()

    private fun certificat(): X509Certificate =
        CertificateFactory.getInstance("X.509")
            .generateCertificate(certPem.byteInputStream()) as X509Certificate

    @Test fun l_empreinte_fait_64_caracteres_hexadecimaux_minuscules() {
        val e = Epinglage.empreinte(certificat())
        assertEquals(64, e.length)
        assertTrue("empreinte non hexadecimale : $e", e.all { it in "0123456789abcdef" })
    }

    @Test fun le_bon_certificat_est_accepte() {
        val attendue = Epinglage.empreinte(certificat())
        GestionnaireEpingle(attendue)
            .checkServerTrusted(arrayOf(certificat()), "RSA")   // ne doit rien lever
    }

    @Test fun un_certificat_inattendu_est_refuse() {
        try {
            GestionnaireEpingle("00".repeat(32))
                .checkServerTrusted(arrayOf(certificat()), "RSA")
            fail("un certificat inattendu a ete accepte")
        } catch (e: CertificateException) {
            // attendu
        }
    }

    @Test fun la_casse_de_l_empreinte_attendue_est_sans_importance() {
        val attendue = Epinglage.empreinte(certificat()).uppercase()
        GestionnaireEpingle(attendue).checkServerTrusted(arrayOf(certificat()), "RSA")
    }
}
```

- [ ] **Step 3 : Vérifier que les tests échouent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*EpinglageTest*'`
Expected: FAIL — `Unresolved reference: Epinglage`

- [ ] **Step 4 : Implémenter**

```kotlin
package fr.izquierdo.phototheque.reseau

import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.X509TrustManager

/**
 * Vérification de l'identité du serveur par l'empreinte de son certificat.
 *
 * Le certificat du NUC est AUTO-SIGNÉ : aucune autorité ne le garantit, donc la
 * validation habituelle échoue toujours. L'épinglage ne s'ajoute pas à cette
 * validation, il la REMPLACE — c'est l'empreinte transmise dans le QR qui fait
 * foi. Une adresse IP change et un nom .local peut être usurpé sur un réseau
 * local ; l'empreinte du certificat, non.
 */
object Epinglage {

    /** SHA-256 du certificat au format DER, en hexadécimal minuscule. */
    fun empreinte(certificat: X509Certificate): String =
        MessageDigest.getInstance("SHA-256")
            .digest(certificat.encoded)
            .joinToString("") { "%02x".format(it) }
}

class GestionnaireEpingle(empreinteAttendue: String) : X509TrustManager {

    private val attendue = empreinteAttendue.lowercase()

    override fun checkServerTrusted(chain: Array<X509Certificate>?, authType: String?) {
        val presente = chain?.firstOrNull()
            ?: throw CertificateException("le serveur n'a presente aucun certificat")
        val obtenue = Epinglage.empreinte(presente)
        // Comparaison en temps constant, par principe : ce n'est pas un secret,
        // mais on ne prend pas l'habitude de comparer des empreintes autrement.
        if (!MessageDigest.isEqual(obtenue.toByteArray(), attendue.toByteArray())) {
            throw CertificateException(
                "certificat inattendu : $obtenue, attendu $attendue")
        }
    }

    /** L'application ne présente jamais de certificat client. */
    override fun checkClientTrusted(chain: Array<X509Certificate>?, authType: String?) =
        throw CertificateException("non utilise")

    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
}
```

- [ ] **Step 5 : Vérifier qu'ils passent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*EpinglageTest*'`
Expected: PASS, 4 tests.

- [ ] **Step 6 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Epinglage.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/reseau/EpinglageTest.kt
git commit -m "feat(android): epinglage du certificat par son empreinte SHA-256"
```

---

### Task 6 : Client HTTP — les quatre appels du contrat

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/ClientServeur.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/reseau/ClientServeurTest.kt`

**Interfaces:**
- Consumes: Task 4 (`Contrat`, modèles), Task 5 (`GestionnaireEpingle`)
- Produces:
  - `class ClientServeur(baseUrl: String, jeton: String, http: OkHttpClient)`
  - `fun horizon(): ReponseHorizon`
  - `fun plan(fichiers: List<FichierPlan>): ReponsePlan`
  - `fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long): ResultatEnvoi`
  - `fun commit(session: String, horizons: Map<String, Double>): Map<String, Double>`
  - `enum class ResultatEnvoi { OK, EXTENSION_REFUSEE, REVOQUE, ECHEC }`

- [ ] **Step 1 : Écrire les tests qui échouent**

```kotlin
package fr.izquierdo.phototheque.reseau

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** Reponses issues de docs/CONTRAT-APP.md, capturees sur un echange reel. */
class ClientServeurTest {

    private lateinit var serveur: MockWebServer
    private lateinit var client: ClientServeur

    @Before fun demarrer() {
        serveur = MockWebServer().also { it.start() }
        client = ClientServeur(serveur.url("/").toString().trimEnd('/'),
                               "jeton-de-test", OkHttpClient())
    }

    @After fun arreter() = serveur.shutdown()

    @Test fun le_jeton_est_envoye_en_bearer() {
        serveur.enqueue(MockResponse().setBody("""{"depuis":null,"dossiers":{}}"""))
        client.horizon()
        assertEquals("Bearer jeton-de-test",
            serveur.takeRequest().getHeader("Authorization"))
    }

    @Test fun horizon_est_lu() {
        serveur.enqueue(MockResponse().setBody(
            """{"depuis":"2026-09-01","dossiers":{"DCIM/Camera":1789000000.0}}"""))
        val r = client.horizon()
        assertEquals("2026-09-01", r.depuis)
        assertEquals(1789000000.0, r.dossiers["DCIM/Camera"]!!, 0.001)
    }

    @Test fun le_plan_renvoie_session_et_empreintes() {
        serveur.enqueue(MockResponse().setBody(
            """{"session":"4bad0393fe5f4fd69635802c39699ce1","needed":["${"ab".repeat(32)}"]}"""))
        val r = client.plan(listOf(FichierPlan("DCIM/a.jpg", 954L, "ab".repeat(32))))
        assertEquals("4bad0393fe5f4fd69635802c39699ce1", r.session)
        assertEquals(1, r.needed.size)
    }

    @Test fun un_400_est_une_extension_refusee_pas_un_echec() {
        // Le contrat est formel : l'application doit POURSUIVRE la synchro.
        serveur.enqueue(MockResponse().setResponseCode(400).setBody(
            """{"detail":"extension non prise en charge : .webm"}"""))
        assertEquals(ResultatEnvoi.EXTENSION_REFUSEE,
            client.envoyer("s".repeat(32), "DCIM/a.webm", "x".byteInputStream(), 1L))
    }

    @Test fun un_401_signale_un_appareil_revoque() {
        serveur.enqueue(MockResponse().setResponseCode(401).setBody(
            """{"detail":"jeton invalide"}"""))
        assertEquals(ResultatEnvoi.REVOQUE,
            client.envoyer("s".repeat(32), "DCIM/a.jpg", "x".byteInputStream(), 1L))
    }

    @Test fun un_500_est_un_echec_ordinaire() {
        serveur.enqueue(MockResponse().setResponseCode(500))
        assertEquals(ResultatEnvoi.ECHEC,
            client.envoyer("s".repeat(32), "DCIM/a.jpg", "x".byteInputStream(), 1L))
    }

    @Test fun le_commit_transmet_les_horizons() {
        serveur.enqueue(MockResponse().setBody("""{"sorted":1,"errors":0}"""))
        client.commit("s".repeat(32), mapOf("DCIM/Camera" to 1789000000.0))

        // On analyse le JSON et on compare la VALEUR, pas sa representation
        // textuelle. Kotlin serialise 1789000000.0 en « 1.789E9 » : c'est du
        // JSON valide, et le vrai serveur le relit bien comme 1789000000.0
        // (verifie en 2026-09-18 par une requete reelle sur /sync/commit puis
        // relecture via /sync/horizon). Chercher la chaine « 1789000000 » dans
        // le corps testerait un detail de formatage au lieu du contrat — et
        // c'est exactement ce que faisait la premiere version de ce test, qui
        // a conduit a remplacer a tort la bibliotheque de serialisation par de
        // la construction JSON a la main.
        val corps = Json.parseToJsonElement(serveur.takeRequest().body.readUtf8()).jsonObject
        assertEquals("s".repeat(32), corps["session"]!!.jsonPrimitive.content)
        assertEquals(
            1789000000.0,
            corps["horizons"]!!.jsonObject["DCIM/Camera"]!!.jsonPrimitive.double,
            0.001)
    }
}
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*ClientServeurTest*'`
Expected: FAIL — `Unresolved reference: ClientServeur`

- [ ] **Step 3 : Implémenter**

```kotlin
package fr.izquierdo.phototheque.reseau

import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okio.BufferedSink
import okio.source
import java.io.InputStream

/** Ce que devient un envoi, du point de vue de la règle de l'horizon. */
enum class ResultatEnvoi {
    /** 200 : le média est chez le serveur. */
    OK,
    /** 400 : extension que le trieur ne sait pas ranger. PAS un échec —
     *  bloquer l'horizon dessus fermerait le dossier à jamais. */
    EXTENSION_REFUSEE,
    /** 401 : l'appareil a été révoqué depuis la page d'administration.
     *  Inutile de réessayer : seul un nouvel appairage débloque. */
    REVOQUE,
    /** Tout le reste. */
    ECHEC,
}

/**
 * Les quatre appels de docs/CONTRAT-APP.md. Aucune intelligence ici : ce module
 * traduit du HTTP, il ne décide de rien.
 */
class ClientServeur(
    private val baseUrl: String,
    private val jeton: String,
    private val http: OkHttpClient,
) {
    private fun requete(chemin: String) = Request.Builder()
        .url("$baseUrl$chemin")
        .header("Authorization", "Bearer $jeton")

    fun horizon(): ReponseHorizon =
        http.newCall(requete("/sync/horizon").get().build()).execute().use { r ->
            Contrat.json.decodeFromString(r.body!!.string())
        }

    fun plan(fichiers: List<FichierPlan>): ReponsePlan {
        val corps = Contrat.json.encodeToString(RequetePlan.serializer(), RequetePlan(fichiers))
            .toRequestBody("application/json".toMediaType())
        return http.newCall(requete("/sync/plan").post(corps).build()).execute().use { r ->
            Contrat.json.decodeFromString(r.body!!.string())
        }
    }

    /**
     * Envoie un média. Le flux est recopié PAR BLOCS par OkHttp : le fichier
     * n'est jamais tenu en mémoire, ce qui compte pour une vidéo de 3 Go sur un
     * téléphone autant que sur le NUC (issue #21).
     */
    fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long): ResultatEnvoi {
        val fichier = object : RequestBody() {
            override fun contentType() = "application/octet-stream".toMediaType()
            override fun contentLength() = taille
            override fun writeTo(sink: BufferedSink) {
                flux.source().use { sink.writeAll(it) }
            }
        }
        val corps = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("session", session)
            .addFormDataPart("path", chemin)
            .addFormDataPart("file", chemin.substringAfterLast('/'), fichier)
            .build()
        return try {
            http.newCall(requete("/sync/upload").post(corps).build()).execute().use { r ->
                when (r.code) {
                    200 -> ResultatEnvoi.OK
                    400 -> ResultatEnvoi.EXTENSION_REFUSEE
                    401 -> ResultatEnvoi.REVOQUE
                    else -> ResultatEnvoi.ECHEC
                }
            }
        } catch (e: Exception) {
            ResultatEnvoi.ECHEC          // réseau coupé, serveur parti
        }
    }

    /**
     * Valide la session. Renvoie les compteurs NUMÉRIQUES du bilan (`sorted`,
     * `duplicates`, `errors`, `photos`…), qui sont ce que l'écran de détail
     * affiche. Les deux champs imbriqués du bilan — `par_source_date` et
     * `par_annee_mois` — sont volontairement écartés ici : ils n'ont pas
     * d'usage dans le lot 1 et les lire demanderait un modèle de plus.
     */
    fun commit(session: String, horizons: Map<String, Double>): Map<String, Double> {
        val corps = Contrat.json
            .encodeToString(RequeteCommit.serializer(), RequeteCommit(session, horizons))
            .toRequestBody("application/json".toMediaType())
        return http.newCall(requete("/sync/commit").post(corps).build()).execute().use { r ->
            val objet = Json.parseToJsonElement(r.body!!.string()) as JsonObject
            objet.mapNotNull { (cle, valeur) ->
                valeur.toString().toDoubleOrNull()?.let { cle to it }
            }.toMap()
        }
    }
}
```

- [ ] **Step 4 : Vérifier qu'ils passent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*ClientServeurTest*'`
Expected: PASS, 7 tests.

- [ ] **Step 5 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/ClientServeur.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/reseau/ClientServeurTest.kt
git commit -m "feat(android): client des quatre appels du contrat serveur"
```

---

### Task 7 : Empreintes SHA-256 en flux

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/medias/Empreintes.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/medias/EmpreintesTest.kt`

**Interfaces:**
- Consumes: rien
- Produces: `Empreintes.sha256(flux: InputStream): String`, `Empreintes.TAILLE_BLOC: Int`

- [ ] **Step 1 : Écrire les tests qui échouent**

```kotlin
package fr.izquierdo.phototheque.medias

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.InputStream

class EmpreintesTest {

    @Test fun empreinte_connue() {
        // sha256("") et sha256("abc"), valeurs de reference universelles.
        assertEquals("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            Empreintes.sha256("".byteInputStream()))
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            Empreintes.sha256("abc".byteInputStream()))
    }

    @Test fun le_fichier_n_est_jamais_lu_entierement_d_un_coup() {
        // Meme propriete que cote serveur (issue #21) : un flux qui refuse la
        // lecture integrale. Sur un telephone, avaler une video de 3 Go tue
        // l'application aussi surement que le service du NUC.
        val contenu = ByteArray(3 * 1024 * 1024) { (it % 251).toByte() }
        var plusGrandeDemande = 0
        val flux = object : InputStream() {
            private var position = 0
            override fun read(): Int = throw AssertionError("lecture octet par octet")
            override fun read(b: ByteArray, off: Int, len: Int): Int {
                if (len > Empreintes.TAILLE_BLOC)
                    throw AssertionError("bloc de $len octets demande, trop gros")
                plusGrandeDemande = maxOf(plusGrandeDemande, len)
                if (position >= contenu.size) return -1
                val n = minOf(len, contenu.size - position)
                contenu.copyInto(b, off, position, position + n)
                position += n
                return n
            }
        }
        Empreintes.sha256(flux)
        assertTrue(plusGrandeDemande in 1..Empreintes.TAILLE_BLOC)
    }

    @Test fun l_implementation_n_accumule_jamais_le_fichier_en_memoire() {
        // Le test precedent ne SUFFIT PAS a interdire l'anti-motif qu'il vise.
        // Verifie en desassemblant le bytecode de kotlin-stdlib : readBytes()
        // copie par blocs de 8192 octets — tres en dessous du seuil d'un Mio —
        // tout en accumulant la totalite du fichier en memoire. Une
        // implementation « digest(flux.readBytes()) » passerait donc les deux
        // autres tests tout en provoquant exactement l'OOM que ce module existe
        // pour eviter.
        //
        // Un test unitaire ne peut pas observer la memoire accumulee par une
        // autre fonction. Il peut en revanche verrouiller l'API interdite.
        val source = java.io.File(
            "src/main/kotlin/fr/izquierdo/phototheque/medias/Empreintes.kt").readText()
        assertFalse(
            "Empreintes.kt ne doit jamais accumuler le fichier en memoire",
            source.contains("readBytes(") || source.contains(".bytes()"))
    }
}
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*EmpreintesTest*'`
Expected: FAIL — `Unresolved reference: Empreintes`

- [ ] **Step 3 : Implémenter**

```kotlin
package fr.izquierdo.phototheque.medias

import java.io.InputStream
import java.security.MessageDigest

/**
 * Empreinte de contenu, lue par blocs.
 *
 * Jamais `readBytes()` : une vidéo de 3 Go tient rarement dans la mémoire
 * autorisée à une application Android, et le processus est tué sans explication.
 * Même raisonnement que côté serveur (issue #21).
 */
object Empreintes {

    const val TAILLE_BLOC = 1024 * 1024      // 1 Mio

    fun sha256(flux: InputStream): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val tampon = ByteArray(TAILLE_BLOC)
        flux.use {
            while (true) {
                val lus = it.read(tampon, 0, TAILLE_BLOC)
                // -1 est la SEULE vraie fin de flux. Traiter 0 comme une fin
                // tronquerait l'empreinte en silence : le media partirait sous
                // une mauvaise identite, ou serait repropose indefiniment, sans
                // exception ni message. Le flux reel est un
                // ContentResolver.openInputStream, parfois adosse a du stockage
                // distant, ou un 0 transitoire est concevable.
                if (lus < 0) break
                if (lus == 0) continue
                digest.update(tampon, 0, lus)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
```

- [ ] **Step 4 : Vérifier qu'ils passent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*EmpreintesTest*'`
Expected: PASS, 3 tests.

- [ ] **Step 5 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/medias/Empreintes.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/medias/EmpreintesTest.kt
git commit -m "feat(android): empreinte SHA-256 lue par blocs"
```

---

### Task 8 : Choix des candidats — la comparaison `>=` à la frontière

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/medias/Media.kt`
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Selection.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/SelectionTest.kt`

**Interfaces:**
- Consumes: Task 2 (`Dates`)
- Produces: `data class Media(id: Long, dossier: String, nom: String, taille: Long, instant: Double)`, `Selection.candidats(medias, dossiersChoisis, horizons, depuisSecondes): List<Media>`

- [ ] **Step 1 : Écrire les tests qui échouent**

```kotlin
package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media
import org.junit.Assert.assertEquals
import org.junit.Test

class SelectionTest {

    private fun media(dossier: String, instant: Double, nom: String = "a.jpg") =
        Media(id = instant.toLong(), dossier = dossier, nom = nom,
              taille = 100L, instant = instant)

    @Test fun seuls_les_dossiers_coches_sont_retenus() {
        val medias = listOf(media("DCIM/Camera", 200.0), media("Pictures/Memes", 200.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"), emptyMap(), 0.0)
        assertEquals(listOf("DCIM/Camera"), r.map { it.dossier })
    }

    @Test fun ce_qui_precede_l_horizon_est_ecarte() {
        val medias = listOf(media("DCIM/Camera", 100.0), media("DCIM/Camera", 300.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"),
                                    mapOf("DCIM/Camera" to 200.0), 0.0)
        assertEquals(listOf(300.0), r.map { it.instant })
    }

    @Test fun le_fichier_exactement_a_l_horizon_est_REPROPOSE() {
        // Comparaison >= et non > : DATE_MODIFIED est en secondes, deux photos
        // d'une rafale peuvent porter la meme valeur. Avec >, la seconde serait
        // perdue a jamais. Reproposer est benin (l'anti-doublon ecarte sans
        // transferer), sauter est definitif. Voir la spec, section 5.
        val medias = listOf(media("DCIM/Camera", 200.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"),
                                    mapOf("DCIM/Camera" to 200.0), 0.0)
        assertEquals(1, r.size)
    }

    @Test fun un_dossier_sans_horizon_retombe_sur_depuis() {
        val medias = listOf(media("DCIM/Camera", 100.0), media("DCIM/Camera", 300.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"), emptyMap(), 200.0)
        assertEquals(listOf(300.0), r.map { it.instant })
    }

    @Test fun depuis_absent_signifie_aucune_limite() {
        // /sync/horizon peut renvoyer depuis = null pour un appareil repris.
        val medias = listOf(media("DCIM/Camera", 1.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"), emptyMap(), null)
        assertEquals(1, r.size)
    }

    @Test fun les_candidats_sortent_tries_par_date_croissante() {
        // C'est ce qui donne un sens a « le dernier confirme » (Horizons).
        val medias = listOf(media("DCIM/Camera", 300.0), media("DCIM/Camera", 100.0),
                            media("DCIM/Camera", 200.0))
        val r = Selection.candidats(medias, setOf("DCIM/Camera"), emptyMap(), null)
        assertEquals(listOf(100.0, 200.0, 300.0), r.map { it.instant })
    }
}
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*SelectionTest*'`
Expected: FAIL — `Unresolved reference: Selection`

- [ ] **Step 3 : Implémenter**

`Media.kt` :

```kotlin
package fr.izquierdo.phototheque.medias

/**
 * Un média du téléphone, tel que MediaStore le décrit.
 *
 * @param dossier chemin relatif sans barre finale, ex. « DCIM/Camera »
 * @param instant date du média en SECONDES (voir synchro.Dates)
 */
data class Media(
    val id: Long,
    val dossier: String,
    val nom: String,
    val taille: Long,
    val instant: Double,
) {
    /** Chemin transmis au serveur dans `path`. */
    val chemin: String get() = "$dossier/$nom"
}
```

`Selection.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media

object Selection {

    /**
     * Les médias à proposer au serveur, triés par date croissante.
     *
     * @param horizons       ce que renvoie /sync/horizon dans `dossiers`
     * @param depuisSecondes plancher pour un dossier absent de `horizons` ;
     *                       `null` signifie « aucune limite », pas « rien ».
     *
     * La comparaison est `>=` et non `>` : l'horizon vaut la date d'un fichier
     * déjà envoyé, et deux médias peuvent porter exactement la même date quand
     * on retombe sur DATE_MODIFIED, qui n'a qu'une précision d'une seconde.
     * Avec `>`, le second serait écarté définitivement. Reproposer coûte un
     * aller-retour que l'anti-doublon du serveur tranche sans transfert ;
     * sauter coûte une photo.
     */
    fun candidats(
        medias: List<Media>,
        dossiersChoisis: Set<String>,
        horizons: Map<String, Double>,
        depuisSecondes: Double?,
    ): List<Media> = medias
        .filter { it.dossier in dossiersChoisis }
        .filter { media ->
            val plancher = horizons[media.dossier] ?: depuisSecondes
            plancher == null || media.instant >= plancher
        }
        .sortedBy { it.instant }
}
```

- [ ] **Step 4 : Vérifier qu'ils passent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*SelectionTest*'`
Expected: PASS, 6 tests.

- [ ] **Step 5 : Valider par mutation**

Remplacer `media.instant >= plancher` par `media.instant > plancher`, relancer :
Expected: `le_fichier_exactement_a_l_horizon_est_REPROPOSE` ÉCHOUE. Restaurer.

- [ ] **Step 6 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/medias/Media.kt \
        android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Selection.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/SelectionTest.kt
git commit -m "feat(android): choix des candidats, comparaison >= a la frontiere"
```

---

### Task 9 : L'orchestrateur

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Orchestrateur.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/OrchestrateurTest.kt`

**Interfaces:**
- Consumes: Tasks 2, 3, 6, 7, 8
- Produces:
  - `interface SourceMedias { fun lister(): List<Media>; fun ouvrir(media: Media): InputStream }`
  - `interface Serveur { fun horizon(): ReponseHorizon; fun plan(f: List<FichierPlan>): ReponsePlan; fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long): ResultatEnvoi; fun commit(session: String, horizons: Map<String, Double>): Map<String, Double> }`
  - `data class Bilan(val envoyes: Int, val refuses: Int, val echecs: Int, val revoque: Boolean, val bilanServeur: Map<String, Double>)`
  - `class Orchestrateur(source, serveur).synchroniser(dossiersChoisis: Set<String>): Bilan`

- [ ] **Step 1 : Écrire les tests qui échouent**

```kotlin
package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media
import fr.izquierdo.phototheque.reseau.*
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.InputStream

class OrchestrateurTest {

    private fun media(instant: Double, nom: String = "a.jpg") =
        Media(instant.toLong(), "DCIM/Camera", nom, 10L, instant)

    /** Serveur simule : on programme le resultat de chaque envoi. */
    private class FauxServeur(
        val horizons: Map<String, Double> = emptyMap(),
        val reclame: (List<FichierPlan>) -> List<String> = { f -> f.map { it.hash } },
        val resultats: MutableList<ResultatEnvoi> = mutableListOf(),
    ) : Serveur {
        var horizonsEnvoyes: Map<String, Double>? = null
        var commitAppele = false
        override fun horizon() = ReponseHorizon(null, horizons)
        override fun plan(f: List<FichierPlan>) = ReponsePlan("a".repeat(32), reclame(f))
        override fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long) =
            if (resultats.isEmpty()) ResultatEnvoi.OK else resultats.removeAt(0)
        override fun commit(session: String, horizons: Map<String, Double>): Map<String, Double> {
            horizonsEnvoyes = horizons; commitAppele = true; return mapOf("sorted" to 1.0)
        }
    }

    private class FausseSource(val medias: List<Media>) : SourceMedias {
        override fun lister() = medias
        override fun ouvrir(media: Media): InputStream = "contenu".byteInputStream()
    }

    @Test fun cas_nominal_tout_est_envoye_et_l_horizon_avance() {
        val serveur = FauxServeur()
        val bilan = Orchestrateur(FausseSource(listOf(media(100.0), media(200.0))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertEquals(2, bilan.envoyes)
        assertEquals(mapOf("DCIM/Camera" to 200.0), serveur.horizonsEnvoyes)
    }

    @Test fun un_echec_au_milieu_arrete_l_horizon_avant_lui() {
        val serveur = FauxServeur(resultats = mutableListOf(
            ResultatEnvoi.OK, ResultatEnvoi.ECHEC, ResultatEnvoi.OK))
        val bilan = Orchestrateur(
            FausseSource(listOf(media(100.0), media(200.0), media(300.0))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertEquals(mapOf("DCIM/Camera" to 100.0), serveur.horizonsEnvoyes)
        assertEquals(1, bilan.echecs)
    }

    @Test fun le_commit_est_appele_MEME_apres_un_echec() {
        // Sans cela les fichiers deja recus resteraient indefiniment dans le
        // depot temporaire du NUC, sans que rien ne les range.
        val serveur = FauxServeur(resultats = mutableListOf(ResultatEnvoi.ECHEC))
        Orchestrateur(FausseSource(listOf(media(100.0))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertTrue(serveur.commitAppele)
    }

    @Test fun une_extension_refusee_ne_compte_pas_comme_un_echec() {
        val serveur = FauxServeur(resultats = mutableListOf(ResultatEnvoi.EXTENSION_REFUSEE))
        val bilan = Orchestrateur(FausseSource(listOf(media(100.0, "a.webm"))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertEquals(0, bilan.echecs)
        assertEquals(1, bilan.refuses)
        assertEquals(mapOf("DCIM/Camera" to 100.0), serveur.horizonsEnvoyes)
    }

    @Test fun une_revocation_arrete_tout_immediatement() {
        val serveur = FauxServeur(resultats = mutableListOf(ResultatEnvoi.REVOQUE))
        val bilan = Orchestrateur(
            FausseSource(listOf(media(100.0), media(200.0))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertTrue(bilan.revoque)
        assertEquals(0, bilan.envoyes)
    }

    @Test fun les_medias_deja_connus_ne_sont_pas_envoyes() {
        // Le serveur ne reclame rien : on ne transfere rien, mais on valide
        // quand meme pour faire avancer l'horizon.
        val serveur = FauxServeur(reclame = { emptyList() })
        val bilan = Orchestrateur(FausseSource(listOf(media(100.0))), serveur)
            .synchroniser(setOf("DCIM/Camera"))
        assertEquals(0, bilan.envoyes)
        assertTrue(serveur.commitAppele)
        assertEquals(mapOf("DCIM/Camera" to 100.0), serveur.horizonsEnvoyes)
    }
}
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*OrchestrateurTest*'`
Expected: FAIL — `Unresolved reference: Orchestrateur`

- [ ] **Step 3 : Implémenter**

```kotlin
package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Empreintes
import fr.izquierdo.phototheque.medias.Media
import fr.izquierdo.phototheque.reseau.*
import java.io.InputStream

interface SourceMedias {
    fun lister(): List<Media>
    fun ouvrir(media: Media): InputStream
}

/** Ce que l'orchestrateur attend du serveur. L'interface existe pour que
 *  l'orchestrateur soit testable sans réseau. */
interface Serveur {
    fun horizon(): ReponseHorizon
    fun plan(fichiers: List<FichierPlan>): ReponsePlan
    fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long): ResultatEnvoi
    fun commit(session: String, horizons: Map<String, Double>): Map<String, Double>
}

data class Bilan(
    val envoyes: Int,
    val refuses: Int,
    val echecs: Int,
    val revoque: Boolean,
    val bilanServeur: Map<String, Double>,
)

/**
 * Enchaîne une synchronisation complète. C'est ici que se rencontrent le choix
 * des candidats (Selection) et la règle de l'horizon (Horizons) ; le reste du
 * module ne fait que les servir.
 */
class Orchestrateur(
    private val source: SourceMedias,
    private val serveur: Serveur,
) {
    fun synchroniser(dossiersChoisis: Set<String>): Bilan {
        val etat = serveur.horizon()
        val depuis = etat.depuis?.let { jourVersSecondes(it) }
        val candidats = Selection.candidats(source.lister(), dossiersChoisis, etat.dossiers, depuis)

        val empreintes = candidats.associateWith { Empreintes.sha256(source.ouvrir(it)) }
        val reponse = serveur.plan(candidats.map {
            FichierPlan(it.chemin, it.taille, empreintes.getValue(it))
        })
        val reclamees = reponse.needed.toSet()

        val envois = mutableListOf<Envoi>()
        var envoyes = 0; var refuses = 0; var echecs = 0; var revoque = false

        for (media in candidats) {                      // déjà triés par date croissante
            val empreinte = empreintes.getValue(media)
            if (empreinte !in reclamees) {
                // Déjà chez le serveur : rien à transférer, mais l'horizon peut
                // passer par-dessus en toute sécurité.
                envois += Envoi(media.dossier, media.instant, Issue.CONFIRME)
                continue
            }
            when (serveur.envoyer(reponse.session, media.chemin,
                                  source.ouvrir(media), media.taille)) {
                ResultatEnvoi.OK -> {
                    envoyes++; envois += Envoi(media.dossier, media.instant, Issue.CONFIRME)
                }
                ResultatEnvoi.EXTENSION_REFUSEE -> {
                    refuses++; envois += Envoi(media.dossier, media.instant, Issue.IGNORE)
                }
                ResultatEnvoi.ECHEC -> {
                    echecs++; envois += Envoi(media.dossier, media.instant, Issue.ECHEC)
                }
                ResultatEnvoi.REVOQUE -> { revoque = true; break }
            }
        }

        // TOUJOURS valider, même après un échec ou une révocation : sinon les
        // fichiers déjà reçus resteraient indéfiniment dans le dépôt temporaire
        // du NUC, sans que rien ne les range.
        val bilanServeur = serveur.commit(reponse.session, Horizons.calculer(envois))
        return Bilan(envoyes, refuses, echecs, revoque, bilanServeur)
    }

    /** « 2026-09-01 » → secondes. Le champ `depuis` du contrat est une DATE
     *  ISO, pas un timestamp : c'est la seule conversion de ce genre. */
    private fun jourVersSecondes(jour: String): Double =
        java.time.LocalDate.parse(jour)
            .atStartOfDay(java.time.ZoneId.systemDefault())
            .toEpochSecond().toDouble()
}
```

- [ ] **Step 4 : Vérifier qu'ils passent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*OrchestrateurTest*'`
Expected: PASS, 6 tests.

- [ ] **Step 5 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Orchestrateur.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/OrchestrateurTest.kt
git commit -m "feat(android): orchestrateur d'une synchronisation complete"
```

---

### Task 10 : Lecture de MediaStore

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/medias/Depot.kt`

**Interfaces:**
- Consumes: Task 2 (`Dates`), Task 8 (`Media`), Task 9 (`SourceMedias`)
- Produces: `class Depot(context: Context) : SourceMedias`, `Depot.dossiers(): Map<String, Int>`, `Depot.accesPartiel(): Boolean`

Cette tâche est de la colle Android : elle ne se teste pas sur la JVM et sera
vérifiée sur le téléphone à la tâche 15. Toute la logique testable en a été
sortie aux tâches 2 et 8 — c'est pour cela qu'il n'en reste presque rien ici.

- [ ] **Step 1 : Implémenter**

```kotlin
package fr.izquierdo.phototheque.medias

import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.MediaStore
import fr.izquierdo.phototheque.synchro.Dates
import fr.izquierdo.phototheque.synchro.SourceMedias
import java.io.InputStream

/**
 * Lecture des photos et vidéos par MediaStore.
 *
 * On n'utilise PAS l'accès direct au système de fichiers ni
 * MANAGE_EXTERNAL_STORAGE : MediaStore suffit, donne RELATIVE_PATH (donc la
 * liste des dossiers sans parcourir le disque) et reste dans les permissions
 * étroites READ_MEDIA_IMAGES / READ_MEDIA_VIDEO.
 */
class Depot(private val context: Context) : SourceMedias {

    private val colonnes = arrayOf(
        MediaStore.MediaColumns._ID,
        MediaStore.MediaColumns.DISPLAY_NAME,
        MediaStore.MediaColumns.RELATIVE_PATH,
        MediaStore.MediaColumns.SIZE,
        MediaStore.MediaColumns.DATE_MODIFIED,
        MediaStore.MediaColumns.DATE_TAKEN,
    )

    override fun lister(): List<Media> =
        interroger(MediaStore.Images.Media.EXTERNAL_CONTENT_URI) +
        interroger(MediaStore.Video.Media.EXTERNAL_CONTENT_URI)

    private fun interroger(uri: android.net.Uri): List<Media> {
        val resultat = mutableListOf<Media>()
        context.contentResolver.query(uri, colonnes, null, null, null)?.use { c ->
            val iId = c.getColumnIndexOrThrow(MediaStore.MediaColumns._ID)
            val iNom = c.getColumnIndexOrThrow(MediaStore.MediaColumns.DISPLAY_NAME)
            val iChemin = c.getColumnIndexOrThrow(MediaStore.MediaColumns.RELATIVE_PATH)
            val iTaille = c.getColumnIndexOrThrow(MediaStore.MediaColumns.SIZE)
            val iModif = c.getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_MODIFIED)
            val iPrise = c.getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_TAKEN)
            while (c.moveToNext()) {
                val prise = if (c.isNull(iPrise)) null else c.getLong(iPrise)
                resultat += Media(
                    id = c.getLong(iId),
                    // RELATIVE_PATH finit par « / » : on la retire pour que le
                    // dossier corresponde exactement aux clés d'horizon du serveur.
                    dossier = c.getString(iChemin).trimEnd('/'),
                    nom = c.getString(iNom),
                    taille = c.getLong(iTaille),
                    instant = Dates.instantSecondes(prise, c.getLong(iModif)),
                )
            }
        }
        return resultat
    }

    override fun ouvrir(media: Media): InputStream {
        val base = if (media.nom.substringAfterLast('.').lowercase() in VIDEOS)
            MediaStore.Video.Media.EXTERNAL_CONTENT_URI
        else MediaStore.Images.Media.EXTERNAL_CONTENT_URI
        val uri = ContentUris.withAppendedId(base, media.id)
        return context.contentResolver.openInputStream(uri)
            ?: throw java.io.IOException("media illisible : ${media.chemin}")
    }

    /** Dossiers présents sur le téléphone et nombre de médias de chacun. */
    fun dossiers(): Map<String, Int> =
        lister().groupingBy { it.dossier }.eachCount()

    /**
     * Vrai si l'utilisateur n'a accordé l'accès qu'à UNE SÉLECTION de photos
     * (Android 14+). L'application fonctionnerait alors normalement en ne
     * sauvegardant que celles-là : c'est le mode de panne silencieux que la
     * conception veut rendre impossible. À afficher en permanence.
     */
    fun accesPartiel(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) return false
        val complet = context.checkSelfPermission(
            android.Manifest.permission.READ_MEDIA_IMAGES) == PackageManager.PERMISSION_GRANTED
        val partiel = context.checkSelfPermission(
            "android.permission.READ_MEDIA_VISUAL_USER_SELECTED") == PackageManager.PERMISSION_GRANTED
        return !complet && partiel
    }

    private companion object {
        val VIDEOS = setOf("mp4", "mkv", "avi", "mov", "m4v", "wmv", "3gp")
    }
}
```

- [ ] **Step 2 : Vérifier que le projet compile toujours**

Run: `cd android && ./gradlew assembleDebug test`
Expected: BUILD SUCCESSFUL, tous les tests précédents toujours verts.

- [ ] **Step 3 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/medias/Depot.kt
git commit -m "feat(android): lecture des medias par MediaStore, detection de l'acces partiel"
```

---

### Task 11 : Appairage — scan du QR et stockage chiffré

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/appairage/Appairage.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/appairage/AppairageTest.kt`

**Interfaces:**
- Consumes: Task 4 (`ChargeAppairage`, `Contrat`)
- Produces: `Appairage.lire(texteDuQr: String): ChargeAppairage?`, `class Coffre(context: Context)` avec `enregistrer(charge)`, `charge(): ChargeAppairage?`, `oublier()`

- [ ] **Step 1 : Écrire les tests qui échouent**

```kotlin
package fr.izquierdo.phototheque.appairage

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AppairageTest {

    @Test fun un_qr_valide_est_lu() {
        val charge = Appairage.lire(
            """{"url":"https://IZQUIERDO-NUC.local:8787","token":"abc","cert_sha256":"${"0f".repeat(32)}"}""")
        assertEquals("abc", charge!!.token)
    }

    @Test fun un_qr_illisible_renvoie_null_sans_lever() {
        // L'utilisateur peut scanner n'importe quel code-barres : un plantage
        // de l'application serait la pire reponse possible.
        assertNull(Appairage.lire("ceci n'est pas du JSON"))
        assertNull(Appairage.lire(""))
        assertNull(Appairage.lire("""{"autre":"chose"}"""))
    }

    @Test fun un_qr_sans_empreinte_reste_valide() {
        // Serveur lance a la main en HTTP : accepte, mais sans epinglage.
        val charge = Appairage.lire("""{"url":"http://x:8787","token":"t","cert_sha256":null}""")
        assertNull(charge!!.certSha256)
    }
}
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*AppairageTest*'`
Expected: FAIL — `Unresolved reference: Appairage`

- [ ] **Step 3 : Implémenter**

```kotlin
package fr.izquierdo.phototheque.appairage

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import fr.izquierdo.phototheque.reseau.ChargeAppairage
import fr.izquierdo.phototheque.reseau.Contrat

object Appairage {
    /** Lit le JSON du QR. Renvoie null sur tout ce qui n'est pas un appairage :
     *  l'utilisateur peut scanner n'importe quel code-barres, et planter serait
     *  la pire des réponses. */
    fun lire(texteDuQr: String): ChargeAppairage? = try {
        Contrat.json.decodeFromString<ChargeAppairage>(texteDuQr)
    } catch (e: Exception) {
        null
    }
}

/**
 * Le jeton est un secret : il ouvre l'envoi de médias sur le NUC. Il est rangé
 * dans les préférences chiffrées d'Android, jamais en clair.
 */
class Coffre(context: Context) {

    private val prefs = EncryptedSharedPreferences.create(
        context,
        "appairage",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    fun enregistrer(charge: ChargeAppairage) = prefs.edit()
        .putString("url", charge.url)
        .putString("token", charge.token)
        .putString("cert", charge.certSha256)
        .apply()

    fun charge(): ChargeAppairage? {
        val url = prefs.getString("url", null) ?: return null
        val token = prefs.getString("token", null) ?: return null
        return ChargeAppairage(url, token, prefs.getString("cert", null))
    }

    /** Appelé sur un 401 : l'appareil a été révoqué, le jeton ne redeviendra
     *  jamais valable. Garder un jeton mort ferait réessayer en boucle. */
    fun oublier() = prefs.edit().clear().apply()
}
```

- [ ] **Step 4 : Vérifier qu'ils passent**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*AppairageTest*'`
Expected: PASS, 3 tests.

- [ ] **Step 5 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/appairage/Appairage.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/appairage/AppairageTest.kt
git commit -m "feat(android): lecture du QR d'appairage et coffre chiffre"
```

---

### Task 12 : Trouver le serveur et construire le client épinglé

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Decouverte.kt`

**Interfaces:**
- Consumes: Tasks 4, 5, 6
- Produces: `Decouverte.adresses(context: Context, delaiMs: Long = 3000): List<String>`, `Fabrique.client(charge: ChargeAppairage): OkHttpClient`, `Fabrique.serveur(context, charge): Serveur?`

**Pourquoi mDNS dès le lot 1 :** Android ne résout pas de manière fiable les noms
en `.local` par le DNS ordinaire. L'`url` du QR seule ne suffirait donc pas à
joindre le NUC, et le lot 1 ne fonctionnerait pas.

- [ ] **Step 1 : Implémenter**

```kotlin
package fr.izquierdo.phototheque.reseau

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import fr.izquierdo.phototheque.synchro.Serveur
import okhttp3.OkHttpClient
import java.io.InputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext

object Decouverte {

    private const val TYPE = "_phototheque._tcp."

    /** Adresses « https://hôte:port » annoncées sur le réseau local. */
    fun adresses(context: Context, delaiMs: Long = 3000): List<String> {
        val nsd = context.getSystemService(Context.NSD_SERVICE) as NsdManager
        val trouvees = mutableListOf<String>()
        val fini = CountDownLatch(1)

        val ecouteur = object : NsdManager.DiscoveryListener {
            override fun onServiceFound(info: NsdServiceInfo) {
                nsd.resolveService(info, object : NsdManager.ResolveListener {
                    override fun onServiceResolved(resolu: NsdServiceInfo) {
                        synchronized(trouvees) {
                            trouvees += "https://${resolu.host.hostAddress}:${resolu.port}"
                        }
                    }
                    override fun onResolveFailed(i: NsdServiceInfo, code: Int) = Unit
                })
            }
            override fun onDiscoveryStarted(type: String) = Unit
            override fun onServiceLost(info: NsdServiceInfo) = Unit
            override fun onDiscoveryStopped(type: String) { fini.countDown() }
            override fun onStartDiscoveryFailed(t: String, c: Int) { fini.countDown() }
            override fun onStopDiscoveryFailed(t: String, c: Int) { fini.countDown() }
        }

        nsd.discoverServices(TYPE, NsdManager.PROTOCOL_DNS_SD, ecouteur)
        fini.await(delaiMs, TimeUnit.MILLISECONDS)
        runCatching { nsd.stopServiceDiscovery(ecouteur) }
        return synchronized(trouvees) { trouvees.toList() }
    }
}

object Fabrique {

    /** Client HTTP qui n'accepte QUE le certificat annoncé dans le QR. */
    fun client(charge: ChargeAppairage): OkHttpClient {
        val empreinte = charge.certSha256 ?: return OkHttpClient()   // serveur sans TLS
        val gestionnaire = GestionnaireEpingle(empreinte)
        val contexte = SSLContext.getInstance("TLS").apply {
            init(null, arrayOf(gestionnaire), java.security.SecureRandom())
        }
        return OkHttpClient.Builder()
            .sslSocketFactory(contexte.socketFactory, gestionnaire)
            // Le certificat est auto-signé et son nom d'hôte peut ne pas
            // correspondre à l'adresse IP trouvée en mDNS. C'est l'empreinte
            // qui fait foi, pas le nom : voir docs/CONTRAT-APP.md section 3.
            .hostnameVerifier { _, _ -> true }
            .build()
    }

    /**
     * Cherche le serveur : d'abord les adresses annoncées en mDNS, puis l'url
     * du QR en secours. Renvoie null si rien ne répond — ce qui veut
     * simplement dire « pas à la maison », et n'est PAS une panne.
     */
    fun serveur(context: Context, charge: ChargeAppairage): Serveur? {
        val http = client(charge)
        for (base in Decouverte.adresses(context) + charge.url) {
            val candidat = ClientServeur(base, charge.token, http)
            val vivant = runCatching { candidat.horizon() }.isSuccess
            if (vivant) return Adaptateur(candidat)
        }
        return null
    }
}

/** Branche ClientServeur (réseau) sur l'interface attendue par l'orchestrateur. */
private class Adaptateur(private val c: ClientServeur) : Serveur {
    override fun horizon() = c.horizon()
    override fun plan(fichiers: List<FichierPlan>) = c.plan(fichiers)
    override fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long) =
        c.envoyer(session, chemin, flux, taille)
    override fun commit(session: String, horizons: Map<String, Double>) =
        c.commit(session, horizons)
}
```

- [ ] **Step 2 : Vérifier que tout compile et que les tests restent verts**

Run: `cd android && ./gradlew assembleDebug test`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 3 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Decouverte.kt
git commit -m "feat(android): decouverte mDNS et client epingle sur l'empreinte du QR"
```

---

### Task 13 : Les écrans

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/EtatSynchro.kt`
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/ModeleAccueil.kt`
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Ecrans.kt`
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/MainActivity.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/EtatSynchroTest.kt`
- Modify: `android/app/src/main/AndroidManifest.xml` (déclarer l'activité)

**Interfaces:**
- Consumes: Tasks 9, 10, 11, 12
- Produces: `data class EtatSynchro(...)`, `EtatSynchro.joursDepuis(maintenantMs, derniereReussiteMs): Long?`, `class ModeleAccueil : ViewModel`

Le lot 1 livre les écrans **appairage**, **accueil** et **détail**. L'écran de
choix des dossiers arrive au lot 2 : ici, les dossiers sont codés en dur.

- [ ] **Step 1 : Écrire le test qui échoue (le compteur de jours)**

```kotlin
package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Le compteur part de la derniere synchro REUSSIE, jamais de la derniere
 * tentative : les pires pannes sont celles ou rien ne se passe, et ou il n'y a
 * donc aucun echec a signaler.
 */
class EtatSynchroTest {

    private val jour = 24 * 3600 * 1000L

    @Test fun jamais_synchronise_ne_donne_aucun_compteur() {
        assertNull(EtatSynchro.joursDepuis(maintenantMs = 10 * jour, derniereReussiteMs = null))
    }

    @Test fun compte_les_jours_entiers_ecoules() {
        assertEquals(3L, EtatSynchro.joursDepuis(10 * jour, 7 * jour))
        assertEquals(0L, EtatSynchro.joursDepuis(10 * jour, 10 * jour))
    }

    @Test fun le_seuil_d_alerte_est_a_sept_jours() {
        assertEquals(7L, EtatSynchro.SEUIL_ALERTE_JOURS)
    }
}
```

- [ ] **Step 2 : Vérifier qu'il échoue**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*EtatSynchroTest*'`
Expected: FAIL — `Unresolved reference: EtatSynchro`

- [ ] **Step 3 : Implémenter l'état**

```kotlin
package fr.izquierdo.phototheque.ui

import fr.izquierdo.phototheque.synchro.Bilan

data class EtatSynchro(
    val enCours: Boolean = false,
    val derniereReussiteMs: Long? = null,
    val dernierBilan: Bilan? = null,
    val accesPartiel: Boolean = false,
    val revoque: Boolean = false,
    val serveurIntrouvable: Boolean = false,
) {
    companion object {
        /** Au-delà, l'accueil passe en avertissement. */
        const val SEUIL_ALERTE_JOURS = 7L

        /** Jours entiers depuis la dernière synchro RÉUSSIE, null si jamais. */
        fun joursDepuis(maintenantMs: Long, derniereReussiteMs: Long?): Long? =
            derniereReussiteMs?.let { (maintenantMs - it) / (24 * 3600 * 1000L) }
    }
}
```

- [ ] **Step 4 : Vérifier qu'il passe**

Run: `cd android && ./gradlew testDebugUnitTest --tests '*EtatSynchroTest*'`
Expected: PASS, 3 tests.

- [ ] **Step 5 : Écrire le modèle de vue**

```kotlin
package fr.izquierdo.phototheque.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import fr.izquierdo.phototheque.appairage.Coffre
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.reseau.Fabrique
import fr.izquierdo.phototheque.synchro.Orchestrateur
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class ModeleAccueil(application: Application) : AndroidViewModel(application) {

    private val coffre = Coffre(application)
    private val depot = Depot(application)
    private val _etat = MutableStateFlow(EtatSynchro())
    val etat = _etat.asStateFlow()

    /** Lot 1 : dossiers en dur. L'écran de choix arrive au lot 2. */
    private val dossiers = setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp")

    fun synchroniser() {
        val charge = coffre.charge() ?: return
        _etat.value = _etat.value.copy(enCours = true, serveurIntrouvable = false)
        viewModelScope.launch(Dispatchers.IO) {
            val serveur = Fabrique.serveur(getApplication(), charge)
            if (serveur == null) {
                // Pas à la maison : ce n'est PAS une panne. Ni notification, ni
                // remise à zéro du compteur de jours.
                _etat.value = _etat.value.copy(enCours = false, serveurIntrouvable = true)
                return@launch
            }
            val bilan = Orchestrateur(depot, serveur).synchroniser(dossiers)
            if (bilan.revoque) coffre.oublier()
            _etat.value = _etat.value.copy(
                enCours = false,
                dernierBilan = bilan,
                revoque = bilan.revoque,
                accesPartiel = depot.accesPartiel(),
                // Réussite = aucun échec. Un refus d'extension n'en est pas un.
                derniereReussiteMs = if (bilan.echecs == 0 && !bilan.revoque)
                    System.currentTimeMillis() else _etat.value.derniereReussiteMs,
            )
        }
    }

    fun enregistrerAppairage(texteDuQr: String): Boolean {
        val charge = fr.izquierdo.phototheque.appairage.Appairage.lire(texteDuQr)
            ?: return false
        coffre.enregistrer(charge)
        _etat.value = _etat.value.copy(revoque = false)
        return true
    }

    fun estAppaire(): Boolean = coffre.charge() != null
}
```

- [ ] **Step 6 : Écrire les écrans**

```kotlin
package fr.izquierdo.phototheque.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun EcranAccueil(etat: EtatSynchro, maintenantMs: Long,
                 surSynchroniser: () -> Unit, surVoirDetail: () -> Unit) {
    val jours = EtatSynchro.joursDepuis(maintenantMs, etat.derniereReussiteMs)
    val alerte = jours == null || jours >= EtatSynchro.SEUIL_ALERTE_JOURS

    Column(Modifier.fillMaxSize().padding(24.dp),
           horizontalAlignment = Alignment.CenterHorizontally,
           verticalArrangement = Arrangement.Center) {

        if (etat.accesPartiel) Bandeau(
            "L'application ne voit qu'une partie de vos photos. " +
            "Autorisez l'accès à toutes les photos dans les réglages Android.")
        if (etat.revoque) Bandeau(
            "Cet appareil a été révoqué. Scannez un nouveau QR sur la page du serveur.")

        Text(
            text = when {
                jours == null -> "Jamais sauvegardé"
                jours == 0L -> "Sauvegardé aujourd'hui"
                jours == 1L -> "Sauvegardé hier"
                else -> "Dernière sauvegarde réussie il y a $jours jours"
            },
            style = MaterialTheme.typography.headlineSmall,
            color = if (alerte) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.onSurface,
        )

        etat.dernierBilan?.let {
            Spacer(Modifier.height(8.dp))
            Text("${it.envoyes} envoyés · ${it.refuses} refusés · ${it.echecs} en échec")
        }
        if (etat.serveurIntrouvable) {
            Spacer(Modifier.height(8.dp))
            // Formulation volontairement neutre : ce n'est pas une panne.
            Text("Serveur introuvable — vous n'êtes probablement pas chez vous.")
        }

        Spacer(Modifier.height(24.dp))
        Button(onClick = surSynchroniser, enabled = !etat.enCours) {
            Text(if (etat.enCours) "Sauvegarde en cours…" else "Sauvegarder maintenant")
        }
        if (etat.enCours) { Spacer(Modifier.height(16.dp)); LinearProgressIndicator() }
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = surVoirDetail) { Text("Voir le détail") }
    }
}

@Composable
private fun Bandeau(texte: String) {
    Card(Modifier.fillMaxWidth().padding(bottom = 16.dp),
         colors = CardDefaults.cardColors(
             containerColor = MaterialTheme.colorScheme.errorContainer)) {
        Text(texte, Modifier.padding(16.dp))
    }
}

@Composable
fun EcranDetail(etat: EtatSynchro) {
    Column(Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState())) {
        Text("Dernière synchronisation", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(16.dp))
        val bilan = etat.dernierBilan
        if (bilan == null) { Text("Aucune synchronisation depuis le lancement.") ; return@Column }
        Text("Envoyés : ${bilan.envoyes}")
        Text("Refusés (extension non gérée) : ${bilan.refuses}")
        Text("En échec : ${bilan.echecs}")
        Spacer(Modifier.height(16.dp))
        Text("Bilan du serveur", style = MaterialTheme.typography.titleMedium)
        bilan.bilanServeur.forEach { (cle, valeur) -> Text("$cle : ${valeur.toInt()}") }
    }
}
```

- [ ] **Step 7 : L'activité et le scan du QR**

```kotlin
package fr.izquierdo.phototheque

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import fr.izquierdo.phototheque.ui.EcranAccueil
import fr.izquierdo.phototheque.ui.EcranDetail
import fr.izquierdo.phototheque.ui.ModeleAccueil

class MainActivity : ComponentActivity() {

    private val modele: ModeleAccueil by viewModels()

    private val scanner = registerForActivityResult(ScanContract()) { resultat ->
        resultat.contents?.let { modele.enregistrerAppairage(it) }
    }

    private val permissions = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        permissions.launch(arrayOf(
            android.Manifest.permission.READ_MEDIA_IMAGES,
            android.Manifest.permission.READ_MEDIA_VIDEO))

        setContent {
            MaterialTheme {
                val etat by modele.etat.collectAsStateWithLifecycle()
                var detail by remember { mutableStateOf(false) }
                when {
                    !modele.estAppaire() || etat.revoque -> {
                        LaunchedEffect(Unit) {
                            scanner.launch(ScanOptions().setPrompt(
                                "Scannez le QR affiché sur la page du serveur"))
                        }
                    }
                    detail -> EcranDetail(etat)
                    else -> EcranAccueil(etat, System.currentTimeMillis(),
                        surSynchroniser = modele::synchroniser,
                        surVoirDetail = { detail = true })
                }
            }
        }
    }
}
```

Déclarer l'activité dans `AndroidManifest.xml`, à l'intérieur de `<application>` :

```xml
<activity android:name=".MainActivity" android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
    </intent-filter>
</activity>
```

- [ ] **Step 8 : Vérifier**

Run: `cd android && ./gradlew assembleDebug test`
Expected: BUILD SUCCESSFUL, tous les tests verts.

- [ ] **Step 9 : Commit**

```bash
git add android/app/src/main android/app/src/test/kotlin/fr/izquierdo/phototheque/ui
git commit -m "feat(android): ecrans appairage, accueil et detail"
```

---

### Task 14 : Le test de contrat, côté serveur

**Files:**
- Create: `tests/test_contrat_app.py`

**Interfaces:**
- Consumes: le serveur Python existant
- Produces: rien pour l'application — c'est un filet côté serveur

**Pourquoi ici et pas côté Kotlin :** la dérive du contrat naît quand quelqu'un
modifie un endpoint. La détecter dans le dépôt serveur, au moment de la
modification, vaut infiniment mieux que la découvrir trois mois plus tard sur un
téléphone qui ne synchronise plus.

- [ ] **Step 1 : Écrire le test**

```python
"""Verrouille le contrat décrit dans docs/CONTRAT-APP.md (issue #15).

Ce fichier n'existe pas pour tester le serveur — les autres s'en chargent — mais
pour que toute modification d'un endpoint qui changerait la FORME des réponses
fasse échouer la suite ici, dans le dépôt où la modification est faite.
L'application Android, elle, code ces formes en dur.
"""

import hashlib
import io


def test_le_qr_porte_exactement_trois_champs(tmp_path, monkeypatch):
    from phototheque import pairing
    charge = pairing.pairing_payload("https://x:8787", "jeton", "ab" * 32)
    assert set(charge) == {"url", "token", "cert_sha256"}, (
        "l'application code ces trois champs en dur ; en ajouter ou en retirer "
        "casse l'appairage de toutes les versions déjà installées")


def test_horizon_renvoie_depuis_et_dossiers(tmp_path, monkeypatch):
    from tests.test_app import _client          # réutilise la fixture existante
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    r = client.get("/sync/horizon", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200
    corps = r.json()
    assert set(corps) == {"depuis", "dossiers"}
    assert isinstance(corps["dossiers"], dict)


def test_plan_renvoie_session_et_empreintes(tmp_path, monkeypatch):
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    entetes = {"Authorization": f"Bearer {secret}"}
    empreinte = hashlib.sha256(b"photo").hexdigest()
    r = client.post("/sync/plan", headers=entetes, json={
        "files": [{"path": "DCIM/a.jpg", "size": 5, "hash": empreinte}]})
    assert r.status_code == 200
    corps = r.json()
    assert set(corps) == {"session", "needed"}
    assert len(corps["session"]) == 32
    # « needed » contient des EMPREINTES, pas des chemins : l'application refait
    # la correspondance elle-même (CONTRAT-APP.md, section 4.2).
    assert corps["needed"] == [empreinte]


def test_les_champs_path_et_size_restent_obligatoires(tmp_path, monkeypatch):
    """Les retirer du contrat sans prévenir donnerait un 422 incompréhensible
    côté téléphone. Voir issue #22 avant de toucher à ce point."""
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    r = client.post("/sync/plan", headers={"Authorization": f"Bearer {secret}"},
                    json={"files": [{"hash": "ab" * 32}]})
    assert r.status_code == 422


def test_une_extension_inconnue_repond_400_et_non_500(tmp_path, monkeypatch):
    """L'application doit POURSUIVRE la synchro sur un 400. Un 500 la ferait
    au contraire s'arrêter et bloquerait l'horizon du dossier."""
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    r = client.post("/sync/upload",
                    headers={"Authorization": f"Bearer {secret}"},
                    data={"session": "a" * 32, "path": "DCIM/note.webm"},
                    files={"file": ("note.webm", io.BytesIO(b"x"), "video/webm")})
    assert r.status_code == 400


def test_un_jeton_revoque_repond_401(tmp_path, monkeypatch):
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    ident, secret = a.devices().pair("tel")
    a.devices().revoke(ident)
    r = client.get("/sync/horizon", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 401


def test_une_session_vide_se_valide_normalement(tmp_path, monkeypatch):
    """Cas COURANT une fois la bibliothèque à jour : rien à envoyer. Répondre
    404 empêcherait l'horizon d'avancer et le téléphone rescannerait sans fin."""
    from tests.test_app import _client
    a, client = _client(tmp_path, monkeypatch)
    _, secret = a.devices().pair("tel")
    entetes = {"Authorization": f"Bearer {secret}"}
    session = client.post("/sync/plan", headers=entetes, json={"files": []}).json()["session"]
    r = client.post("/sync/commit", headers=entetes,
                    json={"session": session, "horizons": {}})
    assert r.status_code == 200
    assert r.json()["errors"] == 0
```

- [ ] **Step 2 : Lancer**

Run: `python3 -m pytest tests/test_contrat_app.py -q`
Expected: PASS, 7 tests. Corriger les imports si `_client` n'est pas importable
tel quel (le déplacer dans `tests/conftest.py` le cas échéant).

- [ ] **Step 3 : Vérifier que la suite complète reste verte**

Run: `python3 -m pytest -q`
Expected: 240 tests (233 + 7).

- [ ] **Step 4 : Commit**

```bash
git add tests/test_contrat_app.py
git commit -m "test(contrat): verrouiller la forme des reponses attendues par l'app"
```

---

### Task 15 : Essai de bout en bout sur le téléphone

**Files:** aucun — c'est la recette du lot.

- [ ] **Step 1 : Installer sur le téléphone**

```bash
cd android && ./gradlew assembleDebug
~/outils/android-sdk/platform-tools/adb devices        # le telephone doit apparaitre
~/outils/android-sdk/platform-tools/adb install -r app/build/outputs/apk/debug/app-debug.apk
```

(Activer d'abord le débogage USB sur le téléphone : Réglages → À propos → appuyer
7 fois sur « Numéro de build », puis Options pour développeurs → Débogage USB.)

- [ ] **Step 2 : Appairer**

Ouvrir `https://IZQUIERDO-NUC.local:8787/pair` sur un ordinateur, lancer
l'application, scanner le QR.

- [ ] **Step 3 : Première synchronisation**

Appuyer sur « Sauvegarder maintenant ». Vérifier, sur le NUC :

```bash
ssh izquierdo@192.168.1.21 'ls -R /media/izquierdo/Famille/Photos/2026 | head -20'
ssh izquierdo@192.168.1.21 'journalctl -u phototheque -n 50 --no-pager'
```

Attendu : les photos rangées par année et mois, aucune erreur dans le journal.

- [ ] **Step 4 : Vérifier que la seconde synchro ne renvoie rien**

Réappuyer sur le bouton. Attendu : `0 envoyés`, et l'horizon a avancé —
c'est la preuve que la règle de l'horizon fonctionne en vrai.

- [ ] **Step 5 : Vérifier l'épinglage**

Sur le NUC, régénérer le certificat (`rm ~/.config/phototheque/cert.pem` puis
`./deploy/install.sh`), puis relancer une synchro depuis le téléphone.
Attendu : **elle échoue**. C'est le comportement voulu — le certificat n'est plus
celui du QR. Réappairer avec le nouveau QR rétablit le fonctionnement.

- [ ] **Step 6 : Vérifier le cas « pas à la maison »**

Couper le Wi-Fi du téléphone, appuyer sur le bouton. Attendu : « Serveur
introuvable — vous n'êtes probablement pas chez vous », **sans** que le compteur
de jours soit touché ni qu'une alerte apparaisse.

- [ ] **Step 7 : Commit de clôture**

```bash
git commit --allow-empty -m "chore(android): lot 1 valide de bout en bout sur telephone reel"
```
