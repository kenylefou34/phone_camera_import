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

        var envoyes = 0; var refuses = 0; var echecs = 0; var revoque = false
        val envois = mutableListOf<Envoi>()

        // Un media devenu illisible est ECARTE du lot plutot que de faire
        // echouer toute la synchronisation. Mais il entre quand meme dans
        // `envois` avec une issue ECHEC : sans cette entree, Horizons.calculer
        // ne le verrait pas, l'horizon du dossier sauterait PAR-DESSUS lui, et
        // il serait perdu definitivement et en silence des la synchro suivante.
        // L'omettre simplement rouvrirait le trou que Horizons.calculer existe
        // pour combler.
        val empreintes = mutableMapOf<Media, String>()
        val lisibles = mutableListOf<Media>()
        for (media in candidats) {
            try {
                empreintes[media] = Empreintes.sha256(source.ouvrir(media))
                lisibles += media
            } catch (e: Exception) {
                echecs++
                envois += Envoi(media.dossier, media.instant, Issue.ECHEC)
            }
        }

        val reponse = serveur.plan(lisibles.map {
            FichierPlan(it.chemin, it.taille, empreintes.getValue(it))
        })
        val reclamees = reponse.needed.toSet()

        for (media in lisibles) {                        // déjà triés par date croissante
            val empreinte = empreintes.getValue(media)
            if (empreinte !in reclamees) {
                // Déjà chez le serveur : rien à transférer, mais l'horizon peut
                // passer par-dessus en toute sécurité.
                envois += Envoi(media.dossier, media.instant, Issue.CONFIRME)
                continue
            }
            // L'ouverture ET l'envoi sont proteges ensemble. ContentResolver
            // peut lever si le media a ete supprime ou deplace entre le listing
            // et maintenant — banal sur un telephone. Sans ce filet, l'exception
            // remonterait hors de synchroniser() et le commit ne serait JAMAIS
            // appele : les fichiers deja recus resteraient indefiniment dans le
            // depot temporaire du NUC, sans que rien ne les range.
            val issue = try {
                when (serveur.envoyer(reponse.session, media.chemin,
                                      source.ouvrir(media), media.taille)) {
                    ResultatEnvoi.OK -> { envoyes++; Issue.CONFIRME }
                    ResultatEnvoi.EXTENSION_REFUSEE -> { refuses++; Issue.IGNORE }
                    ResultatEnvoi.ECHEC -> { echecs++; Issue.ECHEC }
                    ResultatEnvoi.REVOQUE -> { revoque = true; null }
                }
            } catch (e: Exception) {
                echecs++
                Issue.ECHEC
            }
            if (issue == null) break          // revoque : on arrete la boucle
            envois += Envoi(media.dossier, media.instant, issue)
        }

        // TOUJOURS valider, même après un échec ou une révocation : sinon les
        // fichiers déjà reçus resteraient indéfiniment dans le dépôt temporaire
        // du NUC, sans que rien ne les range.
        val bilanServeur = serveur.commit(reponse.session, Horizons.calculer(envois))
        return Bilan(envoyes, refuses, echecs, revoque, bilanServeur)
    }

    /**
     * « 2026-09-01 » → secondes. Le champ `depuis` du contrat est une DATE ISO
     * nue, sans fuseau : il faut donc choisir a quel instant elle commence.
     *
     * On l'ancre a UTC+14, c'est-a-dire l'instant le plus PRECOCE auquel cette
     * date calendaire commence ou que ce soit sur Terre. Interpreter la date
     * dans le fuseau courant du telephone paraitrait plus naturel, mais un
     * changement de fuseau entre l'appairage et la synchro decalerait le
     * plancher — et vers l'ouest il reculerait trop tard, sautant en silence
     * des medias autour de la date d'appairage. Le sens choisi ici ne peut que
     * reproposer quelques heures de trop, que l'anti-doublon ecarte sans les
     * transferer.
     */
    private fun jourVersSecondes(jour: String): Double =
        java.time.LocalDate.parse(jour)
            .atStartOfDay(java.time.ZoneOffset.ofHours(14))
            .toEpochSecond().toDouble()
}
