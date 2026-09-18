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
