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
    /**
     * Vrai si le média vient de la collection Video de MediaStore.
     *
     * Cette information est CONNUE au moment de la lecture : c'est l'URI de
     * collection interrogée qui la donne. La jeter puis la redeviner depuis
     * l'extension du nom échoue sur un fichier sans extension — cas réel pour
     * un média reçu puis renommé.
     */
    val estVideo: Boolean = false,
) {
    /** Chemin transmis au serveur dans `path`. */
    val chemin: String get() = "$dossier/$nom"
}
