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
) {
    /** Chemin transmis au serveur dans `path`. */
    val chemin: String get() = "$dossier/$nom"
}
