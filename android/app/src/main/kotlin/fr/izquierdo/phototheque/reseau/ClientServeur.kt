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
 * Ce qui empêche de joindre le serveur, quand ce n'est PAS « on n'est pas à la
 * maison ».
 *
 * Distinguer ces cas est vital : la conception veut que « pas à la maison »
 * soit SILENCIEUX, et que tout le reste soit VISIBLE. Les confondre rend
 * l'application muette sur les seules pannes qui exigent une action — ici, un
 * appareil révoqué, qui ne se débloquera JAMAIS tout seul.
 */
class ServeurRevoqueException : Exception("appareil revoque")

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

    /**
     * Lit le CODE avant le corps, dans les quatre appels.
     *
     * Sans cela, un 401 (« {"detail":"jeton invalide"} ») ne ressemble à rien de
     * connu, la désérialisation échoue, et l'exception obtenue est la MÊME que
     * celle d'un serveur injoignable : un appareil révoqué afficherait
     * « serveur introuvable » pour toujours.
     */
    private fun verifierCode(r: okhttp3.Response, quoi: String) {
        if (r.code == 401) throw ServeurRevoqueException()
        if (!r.isSuccessful) throw java.io.IOException("$quoi : le serveur a répondu ${r.code}")
    }

    fun horizon(): ReponseHorizon =
        http.newCall(requete("/sync/horizon").get().build()).execute().use { r ->
            verifierCode(r, "horizon refusé")
            Contrat.json.decodeFromString(r.body!!.string())
        }

    fun plan(fichiers: List<FichierPlan>): ReponsePlan {
        val corps = Contrat.json.encodeToString(RequetePlan.serializer(), RequetePlan(fichiers))
            .toRequestBody("application/json".toMediaType())
        return http.newCall(requete("/sync/plan").post(corps).build()).execute().use { r ->
            verifierCode(r, "plan refusé")
            Contrat.json.decodeFromString(r.body!!.string())
        }
    }

    /**
     * Envoie un média. Le flux est recopié PAR BLOCS par OkHttp : le fichier
     * n'est jamais tenu en mémoire, ce qui compte pour une vidéo de 3 Go sur un
     * téléphone autant que sur le NUC (issue #21).
     *
     * @param empreinteAttendue le SHA-256 déjà calculé pour /sync/plan. Le
     *        serveur renvoie l'empreinte du fichier TEL QUE REÇU : les comparer
     *        est le seul moyen de repérer un transfert abîmé.
     */
    fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long,
                empreinteAttendue: String): ResultatEnvoi {
        val fichier = object : RequestBody() {
            override fun contentType() = "application/octet-stream".toMediaType()
            override fun contentLength() = taille
            // Le flux n'est pas rembobinable : OkHttp ne doit JAMAIS rejouer ce
            // corps, sinon il enverrait du vide sous la taille annoncée — et le
            // serveur rangerait un fichier tronqué. isOneShot vaut false par
            // défaut, ce qui l'y autorise.
            override fun isOneShot() = true
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
                    200 -> {
                        // Le contrat renvoie l'empreinte du fichier TEL QUE
                        // REÇU. Une différence signale un transfert abîmé :
                        // l'accepter ferait avancer l'horizon par-dessus
                        // l'original sain, et la bibliothèque garderait la copie
                        // corrompue sans que rien ne le signale.
                        val recu = Contrat.json
                            .decodeFromString<ReponseUpload>(r.body!!.string()).hash
                        if (recu.equals(empreinteAttendue, ignoreCase = true))
                            ResultatEnvoi.OK
                        else ResultatEnvoi.ECHEC
                    }
                    // EXTENSION_REFUSEE est la SEULE issue qui fait avancer
                    // l'horizon sur un média non transféré : elle doit donc
                    // être la plus étroite possible. Or le serveur renvoie
                    // aussi 400 sur un chemin refusé (sessions.save_upload lève
                    // ValueError sur un chemin commençant par « / »), cas où
                    // l'horizon ne doit surtout PAS avancer — le média serait
                    // perdu définitivement et en silence.
                    400 -> if (r.peekBody(4096).string().contains("extension"))
                               ResultatEnvoi.EXTENSION_REFUSEE
                           else ResultatEnvoi.ECHEC
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
            // Sur 401/404/500, le corps s'analysait sans lever et donnait une
            // map vide : l'application croyait avoir réussi alors que AUCUN
            // horizon n'avait été enregistré, et le compteur de jours repartait
            // à zéro en mentant. C'est le dernier maillon du silence.
            verifierCode(r, "commit refusé")
            val objet = Json.parseToJsonElement(r.body!!.string()) as? JsonObject
                ?: throw java.io.IOException("bilan du commit illisible")
            objet.mapNotNull { (cle, valeur) ->
                valeur.toString().toDoubleOrNull()?.let { cle to it }
            }.toMap()
        }
    }
}
