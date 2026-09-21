package fr.izquierdo.phototheque.synchro

/** Les trois phases d'une synchronisation, telles qu'affichées. */
enum class Phase {
    /** Le téléphone calcule les empreintes. Rien ne part sur le réseau —
     *  2 min 08 s mesurées le 21/09, pendant lesquelles l'écran semblait figé. */
    ANALYSE,
    ENVOI,
    /** Le serveur trie le paquet. Peut durer plusieurs minutes. */
    RANGEMENT,
}

/**
 * Instantané immuable de la progression, publié par l'orchestrateur et
 * consommé par l'écran comme par la notification.
 *
 * Immuable et sans référence à Android : l'écran peut disparaître et revenir,
 * l'objet reste valable, et il se teste sur la JVM.
 */
data class Avancement(
    val phase: Phase = Phase.ANALYSE,
    val fichiersFaits: Int = 0,
    val fichiersTotal: Int = 0,
    val octetsFaits: Long = 0L,
    val octetsTotal: Long = 0L,
    val octetsParSeconde: Double? = null,
    val secondesRestantes: Long? = null,
    /** Chemin sur le téléphone, ex. `DCIM/Camera/VID_20250927_164822.mp4`. */
    val mediaEnCours: String? = null,
    val tailleEnCours: Long? = null,
    /** Ex. `Videos/2025/09 SEPTEMBRE`. Estimation : voir [Destination]. */
    val destinationPrevue: String? = null,
    val paquetCourant: Int = 0,
    val paquetsValides: Int = 0,
    /** Dossiers réellement vus sur le téléphone, avec leur nombre de médias. */
    val dossiersVus: Map<String, Int> = emptyMap(),
) {
    /**
     * Calculé sur les OCTETS, jamais sur le nombre de fichiers : neuf petites
     * photos suivies d'une vidéo de 900 Mo annonceraient 90 % alors que
     * l'essentiel du travail reste à faire.
     */
    val pourcentage: Int
        get() = if (octetsTotal <= 0L) 0
                else ((octetsFaits * 100 / octetsTotal).toInt()).coerceIn(0, 100)
}
