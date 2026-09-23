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

/** Corps de POST /sync/abandon (lot serveur, issue #30). */
@Serializable
data class RequeteAbandon(val session: String)

/** Réponse de POST /sync/desappairer (lot 2, tâche 10) : vrai si l'appareil
 *  a bien été retiré côté serveur. */
@Serializable
data class ReponseDesappairage(val retire: Boolean)
