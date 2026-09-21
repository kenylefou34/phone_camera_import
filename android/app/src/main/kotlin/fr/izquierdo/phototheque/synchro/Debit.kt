package fr.izquierdo.phototheque.synchro

/**
 * Débit moyen sur une fenêtre glissante, et estimation du temps restant.
 *
 * L'instant est TOUJOURS un paramètre, jamais lu d'une horloge : sans cela la
 * classe ne serait testable qu'avec des `Thread.sleep`, c'est-à-dire pas
 * testable du tout.
 *
 * Fenêtre glissante et non moyenne depuis le début : une vidéo de 900 Mo
 * envoyée il y a cinq minutes ne doit plus peser sur l'estimation d'un lot de
 * petites photos. C'est précisément l'erreur qui, le 17/09, a fait annoncer
 * 1 h pour un travail de 16 min.
 */
class Debit(private val fenetreMs: Long = 30_000L) {

    /** (instant, octets cumulés depuis le début de la synchronisation). */
    private val mesures = ArrayDeque<Pair<Long, Long>>()

    /** @param octets total cumulé, pas l'incrément. */
    fun ajouter(octets: Long, instantMs: Long) {
        mesures.addLast(instantMs to octets)
        while (mesures.size > 2 && instantMs - mesures.first().first > fenetreMs) {
            mesures.removeFirst()
        }
    }

    /** Octets par seconde, ou null tant qu'on ne peut rien dire d'honnête. */
    fun octetsParSeconde(): Double? {
        if (mesures.size < 2) return null
        val (t0, o0) = mesures.first()
        val (t1, o1) = mesures.last()
        val duree = t1 - t0
        if (duree <= 0L) return null
        return (o1 - o0) * 1000.0 / duree
    }

    /**
     * Secondes restantes, ou null si l'estimation serait inventée.
     *
     * Un débit nul rendrait `Infinity`, et l'écran afficherait « ~ Infinity
     * min ». Mieux vaut ne rien afficher.
     */
    fun secondesRestantes(octetsRestants: Long): Long? {
        if (octetsRestants <= 0L) return 0L
        val debit = octetsParSeconde() ?: return null
        if (debit <= 0.0) return null
        return (octetsRestants / debit).toLong()
    }
}
