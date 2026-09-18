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
