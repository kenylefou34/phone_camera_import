package fr.izquierdo.phototheque.synchro

import java.time.Instant
import java.time.ZoneOffset

/**
 * Où le serveur rangera probablement ce média. **Affichage seulement.**
 *
 * C'est la seule unité de l'application qui duplique une logique du serveur
 * (`mediasort.classify.destination`). Le serveur reste seul juge : il lit les
 * métadonnées du fichier, que le téléphone ne relit pas, et peut donc trancher
 * une autre date. Cette estimation existe parce que « → Videos/2025/09
 * SEPTEMBRE » à l'écran vaut mieux que rien pendant une heure d'envoi.
 *
 * Un test de contrat côté Python (`tests/test_contrat_app.py`) vérifie que les
 * deux conventions ne divergent pas.
 */
object Destination {

    private val MOIS = arrayOf(
        "JANVIER", "FEVRIER", "MARS", "AVRIL", "MAI", "JUIN",
        "JUILLET", "AOUT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DECEMBRE",
    )

    /**
     * @param cheminSource chemin sur le téléphone, ex. `Pictures/WhatsApp/a.jpg`
     * @return chemin relatif à la bibliothèque, sans le nom du fichier
     *
     * L'instant est interprété en UTC, comme le fait le serveur : il travaille
     * sur des `datetime` naïfs issus des métadonnées.
     */
    fun dossier(instantSecondes: Double, estVideo: Boolean, cheminSource: String): String {
        val date = Instant.ofEpochSecond(instantSecondes.toLong()).atZone(ZoneOffset.UTC)
        val racine = if (estWhatsApp(cheminSource)) "WhatsApp/" else ""
        val type = if (estVideo) "Videos" else "Photos"
        val mois = String.format("%02d %s", date.monthValue, MOIS[date.monthValue - 1])
        return "$racine$type/${date.year}/$mois"
    }

    /** Même règle que `mediasort.classify.is_whatsapp` : n'importe quel
     *  segment du chemin qui contient « whatsapp », sans égard à la casse. */
    private fun estWhatsApp(chemin: String): Boolean =
        chemin.split('/').any { it.lowercase().contains("whatsapp") }
}
