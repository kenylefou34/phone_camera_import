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
